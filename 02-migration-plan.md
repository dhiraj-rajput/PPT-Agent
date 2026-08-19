# Integration Plan v2 — linki as a Standalone Hosted Service, PPT-Agent as an API Client

This replaces the previous "port PPT-Agent code into linki's repo" plan. The direction has changed to a **service-extraction model**:

- **linki** stays its own project, gets hosted independently, and gains: (a) the AI-enabled add-ons it's currently missing (CRM Pipeline, LinkedIn AI, Email AI, recurring Newsletter campaigns), and (b) a versioned, API-key-secured external API.
- **PPT-Agent** stops running its own local implementations of LinkedIn Outreach, Email Campaign, Newsletter, and CRM Pipeline. That code is archived (not deleted) into a hidden folder inside the PPT-Agent repo. PPT-Agent becomes a **client** of linki: it pushes company/people data to linki over the API, triggers campaigns/pipelines on linki's server, and pulls results back to render in its own UI.
- **linki's existing LinkedIn engine is not touched** — everything here is additive (new modules, new tables, new API surface). Nothing in `lib/linkedin/*` is modified except where explicitly noted (adding an AI hook point, not changing send logic).

---

## Part A — New AI-enabled add-ons inside linki

These are genuinely new capabilities linki doesn't have today (confirmed in the earlier comparison report) — they slot in alongside the existing engine, they don't replace anything.

### A.1 CRM Pipeline (new, AI-assisted — not a plain port)

Rather than porting PPT-Agent's static 6-column Kanban as-is (which had 3 columns with no linki-native data source), build a linki-native pipeline with an AI layer on top:

- **`lib/pipeline/aggregate.ts`** — stage buckets built from linki's own tables: `Prospects` (`targets` with no workflow run yet), `Contacted` (`connection_requested_at`/`message_sent_at` set), `Replied` (`last_replied_at` set), `Won`/`Lost` (new manual stage field, see below).
- **`lib/pipeline/stage.ts`** — a new `pipeline_stage` column on `targets` (`prospect | contacted | replied | negotiating | won | lost`), settable manually from the UI (drag-and-drop, which PPT-Agent's version didn't even have) and auto-advanced by workflow events (e.g. a reply auto-moves a target from `contacted` → `replied`).
- **`lib/ai/pipeline-insights.ts`** — the AI add-on: given a target's stage, message history, and score/grade (see A.3), generate a short "next best action" suggestion ("no reply in 5 days — consider a follow-up with a case study angle") and a stall/risk flag for deals sitting too long in one stage. Runs on-demand (button in the UI) and optionally as a nightly batch job.
- **UI**: `pages/pipeline.tsx` + `components/pipeline/PipelineBoard.tsx`, drag-and-drop stage changes (new — PPT-Agent's was click-through only), an "AI insight" chip per card.

### A.2 LinkedIn AI add-ons (new modules, engine untouched)

- **`lib/ai/reply-classify.ts`** — port the *prompt logic* (not the send engine) from PPT-Agent's `classify_reply_intent()`. Hooked into linki's existing reply-sync path (`lib/linkedin/sync-accepted.ts` / wherever inbound LinkedIn replies land today) as a pure "read the message, tag it" step — it never touches `lib/linkedin/connect.ts`, `session.ts`, or `runner.ts`'s send logic.
- **Output**: a `reply_intent` tag (`interested | not_interested | referral | question | out_of_office | unsubscribe_request`) stored on the relevant row and surfaced as a badge in `pages/inbox.tsx`.
- This is additive-only: if the AI call fails or is disabled, the inbox behaves exactly as it does today (no intent badge, nothing else changes).

### A.3 Email AI add-ons (new modules, sender untouched)

- **`lib/ai/beautify-email.ts`** — direct port of PPT-Agent's plain-text-to-HTML feature (3 style presets, inline-CSS email-client rules, graceful fallback template). Called from a new "Beautify with AI" button in the email-track step editor in `pages/workflows/[id].tsx`. It only transforms the `emailBody` field the user already wrote — it doesn't change how/when the email is sent.
- **`lib/scoring/lead-score.ts`** — cold/warm/hot/SQL grading (ported thresholds from PPT-Agent's `email_worker.py::classify_score()`), hooked into send/open/click/reply events. Purely additive metadata (`targets.score`, `targets.grade`), doesn't gate or change sending behavior.
- **`lib/email/tracking.ts` + `lib/email/suppression.ts`** — open/click pixel tracking and unsubscribe/suppression list, since these are prerequisites for both the scoring feature above and for computing real open/click/reply rate percentages (linki's dashboard currently only has raw counts).

### A.4 Newsletter as a first-class, recurring campaign type

This is the one place the requirements changed meaningfully: **newsletter must support recurring sends to a selected list/segment, run the same way a LinkedIn/email campaign runs** — not a one-off "edition" model like PPT-Agent's.

Design: treat newsletter as a **third track type** inside linki's existing campaign concept, reusing the same machinery that already runs LinkedIn and email tracks, rather than inventing a parallel newsletter-specific engine:

- **Schema**: `newsletters` table gets `target_list_id` (FK to linki's existing `lists` table — the "selected campaign"/segment concept already used by LinkedIn and email tracks) and recurrence fields: `schedule_type` (`once | daily | weekly | custom_cron`), `schedule_time` (`HH:mm` + timezone), `cron_expression` (for `custom_cron`), `next_run_at`, `last_run_at`, `active` (boolean pause/resume, matching the pause/resume pattern already used for LinkedIn accounts and workflows).
- **`lib/newsletter/schedule.ts`** — a tick function (`checkDueNewsletters()`) that runs on the same kind of interval loop linki already uses. **Hook point**: `instrumentation.ts` currently calls `ensureGlobalRunnerStarted()` on boot to start the LinkedIn runner loop — add a sibling `ensureNewsletterSchedulerStarted()` call there, started the same way, so newsletter recurrence doesn't need a separate cron/infra dependency.
- **`lib/newsletter/send.ts`** — on each due run: resolve subscribers from `target_list_id` (same list-resolution helper the email/LinkedIn tracks already use to pull targets out of a list), filter out `suppressions`, send via the existing `lib/email/sender.ts`, embed tracking pixel/unsubscribe link (A.3), write `newsletter_sends` rows, advance `next_run_at`.
- **UI**: the newsletter edition editor gains the same "Audience" + "Schedule" panels already present in the LinkedIn/email workflow step editor (`pages/workflows/[id].tsx`) — reuse those components (`AudiencePicker`, whatever the existing schedule/timezone controls are called there) instead of building new ones, so a user configuring a newsletter sees the same UI patterns they already know from campaigns.
- **Net result**: "run the same kind of campaign for the newsletter" is satisfied structurally — a newsletter is now a scheduled, list-targeted send just like the other two tracks, sharing the audience-selection and scheduling UI/logic instead of duplicating it.

### A.5 Folder structure inside linki (unchanged from before, consolidated here)

```
linki-main/
├─ lib/
│  ├─ linkedin/            # EXISTING — untouched send/session engine
│  ├─ email/
│  │  ├─ sender.ts         # EXISTING — untouched core send call
│  │  ├─ inbox.ts          # EXISTING
│  │  ├─ tracking.ts       # NEW
│  │  ├─ suppression.ts    # NEW
│  │  └─ scheduler.ts      # NEW — working-hours/daily-limit gating
│  ├─ newsletter/
│  │  ├─ subscribers.ts    # NEW
│  │  ├─ editions.ts       # NEW
│  │  ├─ send.ts           # NEW
│  │  └─ schedule.ts       # NEW — recurrence engine
│  ├─ pipeline/
│  │  ├─ aggregate.ts      # NEW
│  │  └─ stage.ts          # NEW
│  ├─ scoring/
│  │  └─ lead-score.ts     # NEW
│  ├─ ai/
│  │  ├─ client.ts         # NEW — consolidated shared AI call, used by all of the below
│  │  ├─ beautify-email.ts # NEW
│  │  ├─ reply-classify.ts # NEW
│  │  └─ pipeline-insights.ts # NEW
│  └─ api/                 # NEW — external API plumbing, see Part C
│     ├─ auth.ts
│     ├─ keys.ts
│     └─ ingest.ts
├─ pages/
│  ├─ newsletters/{index,[id]}.tsx   # NEW
│  ├─ pipeline.tsx                    # NEW
│  └─ api/
│     ├─ newsletters/...              # NEW — internal (session-authed) CRUD
│     ├─ pipeline.ts                  # NEW
│     ├─ track/{open,click,unsubscribe}/...  # NEW
│     └─ v1/...                       # NEW — external (API-key-authed), see Part C
```

---

## Part B — linki's external API (Part C, detailed)

### C.1 Why a separate API surface, not the existing session-authed `pages/api/*`

linki's current `pages/api/*` routes are gated by `isAuthenticated()` in `lib/auth.ts`, which accepts either a NextAuth session cookie (browser) or `INTERNAL_API_SECRET` (loopback-only, server-to-server, e.g. linki's own MCP server calling itself). Neither is right for PPT-Agent: it's an external server, not a browser, and it shouldn't share the loopback-only internal secret (that secret is explicitly documented as "never sent to a browser or exposed externally" — reusing it for a real external integration would violate its own design intent).

**Decision: add a new, versioned, API-key-authed surface at `pages/api/v1/*`**, kept completely separate from both the browser session routes and the internal loopback secret.

### C.2 API key system

- **`lib/api/keys.ts`**: generate/list/revoke API keys. Each key: `id`, `name` (e.g. "PPT-Agent production"), `hashed_key` (store a hash, not the raw key — same pattern as password storage in `lib/auth.ts`), `scopes` (e.g. `ingest:write`, `campaigns:trigger`, `pipeline:read`), `created_at`, `last_used_at`, `revoked_at`.
- **New table** (added to `lib/db.ts`'s migration set):
  ```sql
  CREATE TABLE IF NOT EXISTS api_keys (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    hashed_key TEXT NOT NULL UNIQUE,
    scopes TEXT NOT NULL DEFAULT '[]',      -- JSON array
    created_at TEXT DEFAULT (datetime('now')),
    last_used_at TEXT,
    revoked_at TEXT
  );
  ```
- **`lib/api/auth.ts`**: `verifyApiKey(req): { keyId, scopes } | null` — reads `Authorization: Bearer <key>`, hashes it, looks it up, checks `revoked_at IS NULL`, checks the required scope for the called route, updates `last_used_at`. Every `pages/api/v1/*` route starts with this check instead of `isAuthenticated()`.
- **Rate limiting**: extend `lib/rate-limit.ts` to key on `api_key_id` instead of (or in addition to) IP, since PPT-Agent will call from a fixed server IP where per-IP limiting alone isn't meaningful. Keep the existing note in that file in mind: it's in-memory/single-process — fine for a single linki instance, but if linki is ever horizontally scaled this limiter (and the SQLite DB itself) would need to move to something shared. Flag this as a known ceiling, not something to solve now.
- **Key issuance UI**: a small settings panel (`pages/settings.tsx`, new tab or section) to generate a key, shown once, with copy-to-clipboard — mirrors how most API-key UIs work, and matches linki's existing single-password-auth simplicity philosophy (no OAuth app registration flow needed for a single external client).

### C.3 External endpoints (`pages/api/v1/*`)

| Endpoint | Method | Purpose | Scope |
|---|---|---|---|
| `/api/v1/companies` | `POST` | Bulk upsert company records pushed from PPT-Agent (maps onto linki's `companies` table) | `ingest:write` |
| `/api/v1/people` | `POST` | Bulk upsert people/prospect records pushed from PPT-Agent (maps onto linki's `targets` table; include a `source_ref` field so results can be matched back to PPT-Agent's own IDs) | `ingest:write` |
| `/api/v1/lists` | `POST` | Create/select the list ("campaign segment") the pushed people belong to | `ingest:write` |
| `/api/v1/campaigns/linkedin` | `POST` | Create + optionally start a LinkedIn track run against a list | `campaigns:trigger` |
| `/api/v1/campaigns/email` | `POST` | Create + optionally start an email track run against a list | `campaigns:trigger` |
| `/api/v1/campaigns/newsletter` | `POST` | Create/update a newsletter (including recurrence config from A.4) targeting a list | `campaigns:trigger` |
| `/api/v1/campaigns/{id}` | `GET` | Poll status (running/paused/completed) and summary stats of any campaign/run | `campaigns:read` |
| `/api/v1/pipeline` | `GET` | Pull current CRM Pipeline board data (Part A.1) — this is what powers PPT-Agent's own pipeline page, see Part D | `pipeline:read` |
| `/api/v1/results/{jobId}` | `GET` | Poll an async job (e.g. a bulk LinkedIn scrape) for completion + result payload | `campaigns:read` |
| `/api/v1/webhooks` | `POST` | Register a callback URL + secret; linki will `POST` to it on key events (reply received, campaign completed, newsletter sent) instead of requiring PPT-Agent to poll everything | `webhooks:manage` |

All request/response bodies get explicit TypeScript interfaces in `lib/api/types.ts` (shared between the route handlers and, ideally, published as a small `.d.ts` PPT-Agent's Python client can reference when generating its own request/response models — see Part D.2).

### C.4 Data flow (the "push data → run on linki → get results back" loop)

```
PPT-Agent                                   linki (separate host)
──────────                                   ─────────────────────
1. POST /api/v1/companies   ──────────────▶  upsert into companies
2. POST /api/v1/people      ──────────────▶  upsert into targets, attach to a list
3. POST /api/v1/campaigns/{linkedin|email|newsletter}
                             ──────────────▶  create + start a run
                                               (linki's EXISTING runner/scheduler
                                                does all the actual work — Playwright
                                                sends, SMTP sends, newsletter recurrence)
4a. GET /api/v1/campaigns/{id}   (poll)   ◀── status + stats
4b. — or —
    linki POSTs to the registered webhook  ──▶ PPT-Agent's callback endpoint
    on reply / completion / newsletter-sent
5. GET /api/v1/pipeline      ◀────────────── current board state, rendered in
                                               PPT-Agent's own CRM Pipeline page
```

Recommend supporting **both** polling (4a) and webhooks (4b): webhooks for near-real-time inbox/reply events (a user waiting on a reply notification shouldn't be on a 30-second poll cycle), polling as the reliable fallback if PPT-Agent's webhook receiver is briefly down.

### C.5 Security & hosting notes for exposing linki externally

- linki's `docker-compose.yml` currently binds `127.0.0.1:${PORT}:3000` — i.e. it's designed to sit behind a reverse proxy (or not be exposed at all) today. Hosting it "as a separate project" reachable by PPT-Agent means either (a) putting a reverse proxy (nginx/Caddy) in front with TLS and forwarding only `/api/v1/*` externally while keeping the browser UI on a VPN/internal network, or (b) exposing the whole app behind its own domain with the existing `AUTH_PASSWORD` protecting the UI and the new API-key layer protecting `/api/v1/*` independently.
- Recommend (a) if the linki UI itself doesn't need to be publicly reachable — smaller attack surface, and it matches the existing "single self-hosted user" design intent of `AUTH_PASSWORD`/`INTERNAL_API_SECRET` more closely.
- API keys should be scoped and rotatable from day one (the `scopes` column above) — PPT-Agent only ever needs `ingest:write` + `campaigns:trigger` + `campaigns:read` + `pipeline:read`, never `webhooks:manage` on a key that's also doing bulk ingestion, so issue **separate keys per concern** rather than one all-powerful key.
- Log every `/api/v1/*` call (caller key id, route, status) to linki's existing `logs` table so there's an audit trail of what PPT-Agent triggered and when — reuse the existing table rather than adding a new one.

---

## Part D — PPT-Agent side changes

### D.1 Archive the old local implementation

Move, don't delete, everything the comparison report identified as belonging to the 4 features, into a single hidden top-level folder so it's out of the active app but still available for reference:

```
PPT-Agent/
└─ .archive/
   └─ linki-integration-2026/
      ├─ README.md                     # explains what this is, when it was archived, why
      ├─ frontend/
      │  ├─ LinkedInOutreach.jsx
      │  ├─ EmailCampaign.jsx
      │  ├─ Newsletter.jsx
      │  ├─ CRMPipeline.jsx
      │  └─ EmailBeautifyModal.jsx
      └─ backend/
         ├─ routes/
         │  ├─ campaigns.py
         │  ├─ leads.py
         │  ├─ tracking.py
         │  ├─ newsletters.py
         │  ├─ linkedin_campaigns.py
         │  ├─ linkedin_inbox.py
         │  └─ linkedin_accounts.py
         ├─ core/
         │  ├─ linkedin_worker.py
         │  ├─ email_worker.py
         │  └─ action_scheduler.py
         ├─ pipeline/linkedin/            # the scraper stack, kept for reference/possible future reuse
         ├─ pipeline/ai/outreach_prompts.py
         └─ scripts/                       # the debug/test scripts documenting the LinkedIn breakage
```

- Prefix the folder with `.` so it's dotfile-hidden from normal directory listings and IDE file trees by default, and add `.archive/` to `.gitignore` **only if** you don't want it version-controlled at all — otherwise keep it tracked but collapsed, since "hidden so it doesn't clutter the active app" and "gone from git history" are different goals; the request here reads as the former (available later, just out of the way), so recommend keeping it in git.
- Do **not** archive the DB models (`sql_models.py`) or run a destructive migration to drop those MySQL tables — leave `Campaign`, `Lead`, `Newsletter`, `LinkedInCampaign`, etc. in place (a no-op migration, tables just stop being written to). Dropping columns/tables in production MySQL is a one-way door; disconnecting the routes/UI is not. Revisit dropping them only after the new API-client approach has been live and stable for a while.

### D.2 Remove from the active app

- `backend/server.py`: remove the 8 `app.include_router(...)` lines for `campaigns_router`, `leads_router`, `tracking_router`, `newsletters_router`, `linkedin_campaigns_router`, `linkedin_inbox_router`, `linkedin_accounts_router`. Leave `analytics_router` in only if any part of it is repurposed to read from linki instead (see D.3) — otherwise remove it too.
- `Frontend/src/pages/`: remove `LinkedInOutreach.jsx`, `EmailCampaign.jsx`, `Newsletter.jsx`, `CRMPipeline.jsx`, and the route entries pointing to them (wherever `App.jsx`'s router config lists these paths) and the corresponding `Sidebar.jsx` nav items.
- `Frontend/src/lib/api.jsx`: remove the now-dead methods (`getCRMPipeline`, `getNewsletters`/newsletter block, the Campaign/Lead block, the LinkedIn campaign/account/inbox block) — or better, replace them in place with the new linki-client calls from D.3 so anything else in the app that happened to import them doesn't silently break.

### D.3 Add a linki API client + thin proxy pages

Since the requirement is "fetch the pages here in the PPT-Agent project for further use" — the *UI* stays in PPT-Agent, but it now renders data sourced from linki instead of PPT-Agent's own DB:

```
PPT-Agent/backend/
└─ integrations/
   └─ linki/
      ├─ __init__.py
      ├─ client.py        # thin HTTP client — reads LINKI_API_URL + LINKI_API_KEY from env,
      │                    #   wraps the /api/v1/* endpoints from Part C.3
      ├─ sync.py           # push_companies(), push_people() — called wherever PPT-Agent
      │                    #   currently creates/updates Company/Person rows, so data
      │                    #   flows to linki automatically as part of existing workflows
      └─ webhooks.py        # FastAPI route(s) receiving linki's webhook callbacks,
                             #   updating local status/cache so the proxy pages have
                             #   something fast to read without hitting linki on every request
```

- **New backend routes** (replacing the removed ones, same paths so the frontend needs minimal change): `backend/app/routes/campaigns.py` etc. become thin proxies — `GET /api/campaigns` now calls `linki.client.list_campaigns()` and reshapes the response instead of querying MySQL directly. Same for pipeline, newsletters, LinkedIn.
- **Local caching**: since every page load shouldn't necessarily round-trip to a second server, cache linki's responses briefly (a `linki_cache` table or even just an in-process TTL cache) and invalidate on webhook events (D.3's `webhooks.py`) — reply received / campaign completed / newsletter sent all trigger a cache refresh for the relevant view.
- **Frontend pages**: `LinkedInOutreach.jsx`/`EmailCampaign.jsx`/`Newsletter.jsx`/`CRMPipeline.jsx` get rebuilt as leaner versions (same visual location/nav entry, much less local state) since all the heavy lifting (send scheduling, tracking, AI) now happens on linki — PPT-Agent's version is a **read + trigger** UI, not an execution engine. Reuse the existing component library (`components/ui/Common.jsx`, `PageHeader`, `Card`) so they look consistent with the rest of PPT-Agent.
- **Config**: add `LINKI_API_URL` and `LINKI_API_KEY` to `backend/.env` / `.env.example`, alongside the existing `SAM_GOV`/`GOOGLE`/etc. integration keys already pattern-matched in `backend/config/settings.py`.

### D.4 Where company/people data comes from on the PPT-Agent side

PPT-Agent already has rich company/people sourcing (Companies House extraction, SAM.gov, the website/LinkedIn research pipeline under `backend/pipeline/`) — none of that is being removed. The only change is the **destination**: instead of that data landing solely in PPT-Agent's own `Company`/`Person` MySQL tables for its own campaigns to use, `integrations/linki/sync.py::push_companies()` / `push_people()` also mirror it to linki via `/api/v1/companies` and `/api/v1/people` so linki's campaigns/pipeline have the same data to work with. Recommend calling `sync.py` at the same point PPT-Agent currently saves a newly-researched company/person, so this is a one-line addition to existing code paths, not a new batch job to maintain.

---

## E — Suggested phase order

| Phase | Work | Where | Est. |
|---|---|---|---|
| 1 | `lib/ai/client.ts` consolidation + `lib/email/tracking.ts` + `suppression.ts` (prereqs for everything else) | linki | 2–2.5 days |
| 2 | `lib/scoring/lead-score.ts`, `lib/email/scheduler.ts` | linki | 2.5 days |
| 3 | `lib/ai/beautify-email.ts`, `lib/ai/reply-classify.ts` | linki | 2 days |
| 4 | CRM Pipeline (`lib/pipeline/*`, `pipeline-insights.ts`, `pages/pipeline.tsx`) | linki | 2–2.5 days |
| 5 | Newsletter as recurring campaign (`lib/newsletter/*`, `instrumentation.ts` hook, UI reuse) | linki | 4 days |
| 6 | API key system + `pages/api/v1/*` external endpoints + webhook dispatch | linki | 3–4 days |
| 7 | Harden hosting: reverse proxy config, scoped keys, audit logging into `logs` | linki (deploy) | 1–1.5 days |
| 8 | Archive PPT-Agent's old code into `.archive/linki-integration-2026/`, remove routers/pages | PPT-Agent | 1 day |
| 9 | `integrations/linki/client.py` + `sync.py` + `webhooks.py`, wire into existing company/person save points | PPT-Agent | 2–3 days |
| 10 | Rebuild the 4 pages as thin proxy/trigger UIs | PPT-Agent | 3–4 days |
| 11 | End-to-end test: push data → trigger each campaign type → confirm results/webhooks land back in PPT-Agent's UI | both | 2 days |

**Total estimate: ~25–30 developer-days**, sequenced so linki's API (Phases 1–7) exists and is stable before PPT-Agent starts depending on it (Phases 8–11) — running 8 before 6/7 would leave PPT-Agent's UI broken with nothing to call.

---

## F — Testing checklist

- [ ] Pushing the same company/person twice via `/api/v1/companies` / `/api/v1/people` upserts, doesn't duplicate (match PPT-Agent's `source_ref` against linki's row).
- [ ] Triggering a LinkedIn campaign via the API produces identical behavior to triggering it from linki's own UI (i.e. the API is a real alternate entry point into the existing runner, not a parallel code path that could drift).
- [ ] A newsletter with `schedule_type: daily` actually fires once per day at the configured time/timezone across a server restart (i.e. `next_run_at` persists and `ensureNewsletterSchedulerStarted()` picks up where it left off).
- [ ] Revoking an API key immediately blocks further calls (no caching of "is this key valid" beyond a very short TTL, if any).
- [ ] Webhook delivery retries on failure (PPT-Agent endpoint down) and doesn't silently drop events — falls back to being caught by the next poll.
- [ ] PPT-Agent's rebuilt pages render correctly with linki fully unreachable (clear "integration offline" state, not a blank page or unhandled exception).
- [ ] The `.archive/` code is confirmed *not* imported anywhere in the active PPT-Agent app (`grep -r "from .archive" backend/` / equivalent returns nothing) so it truly is dead weight, not silently still running.
- [ ] Old PPT-Agent MySQL tables (`Campaign`, `Lead`, `Newsletter`, `LinkedIn*`) are left intact and readable, in case a rollback to the old local implementation is ever needed before those tables are eventually retired.
