# Comparison Report — PPT-Agent (LinkedIn / Email / Newsletter / CRM Pipeline) vs. linki

Scope: this report only covers the 4 PPT-Agent pages you named — **LinkedIn Outreach**, **Email Campaign**, **Newsletter**, **CRM Pipeline** — compared against linki's equivalent (or missing) functionality. Everything else in PPT-Agent (RFP/proposal generation, tenders, SAM.gov, Companies House research, etc.) is out of scope and not touched.

---

## 1. Architecture snapshot

| | **linki** | **PPT-Agent** |
|---|---|---|
| Stack | Next.js 16 (Pages Router) + TypeScript, single monolith | Python/FastAPI backend + separate React 18/Vite frontend (JS, not TS) |
| Database | SQLite (`better-sqlite3`), one file, ~30 tables | MySQL via SQLAlchemy async, ~39 models (`backend/models/sql_models.py`) — code comments say it's a port off an earlier MongoDB schema |
| LinkedIn automation | `playwright-extra` + `puppeteer-extra-plugin-stealth`, single consistent browser fingerprint (login and runtime use identical `contextOptions()`) | Raw `playwright`, opens an "authenticated context" by replaying cookies; also several one-off scripts hitting LinkedIn's internal Voyager API directly |
| Email sending | `nodemailer` (SMTP) + `imap-simple` (IMAP) for inbox/replies | SMTP + IMAP as well, but with a scheduler (working-hours-aware, daily-limit-aware) and pixel/click tracking |
| AI | Multi-provider (OpenAI/Anthropic/Google/Mistral/Qwen) via an OpenRouter-style model picker, **per-workflow-step**, model list served by an `ee/`-only route not present in this public zip | Single `OllamaAIClient` abstraction with a fallback chain (local Ollama → Gemini → OpenRouter), used for 3 fixed purposes: connection notes, follow-ups, reply classification, email beautify |
| Multi-tenancy | Single-tenant, NextAuth session only, no roles | Full user/role system (`UsersRoles.jsx`, `AdminRoute.jsx`, audit log, login-failure tracking, OTP) |
| Commercial features | "Open-core": `lib/premium.ts` bridges to an `ee/` folder that is stripped from this public zip (this is why `/api/openrouter/models` is referenced in the frontend but the route itself isn't in the zip) | No open-core split — everything in one codebase |

**Key structural difference that drives the whole migration plan:** in linki, LinkedIn and Email are **not separate features** — they're two "tracks" inside one `Workflow` (see `pages/workflows/[id].tsx`, `Track = "linkedin" | "email"`). PPT-Agent keeps them as two completely separate systems (`campaigns` vs `linkedin_campaigns`, separate tables, separate pages). This matters for where new features should be *inserted*, not just added.

---

## 2. File location map (inside the PPT-Agent zip)

### LinkedIn Outreach (currently broken)
| Layer | File |
|---|---|
| Frontend page | `Frontend/src/pages/LinkedInOutreach.jsx` (2,361 lines) |
| Frontend API client | `Frontend/src/lib/api.jsx` — methods `listLinkedInCampaigns`, `createLinkedInCampaign`, `getLinkedInTargets`, `getLinkedInQueue`, `getLinkedInTargetMessages`, `reviewLinkedInMessage`, `resendLinkedInMessage`, `getLinkedInInbox`, `sendLinkedInReply`, `getLinkedInAccounts`, `createLinkedInAccount`, `pauseLinkedInAccount`, `resumeLinkedInAccount`, `deleteLinkedInAccount` (lines ~875–945) |
| Backend routes | `backend/app/routes/linkedin_campaigns.py`, `backend/app/routes/linkedin_inbox.py`, `backend/app/routes/linkedin_accounts.py` |
| Automation engine (the broken part) | `backend/app/core/linkedin_worker.py` — `send_connection_request_playwright()`, `poll_inbox_playwright()`, `check_invitation_acceptances()`, `scrape_linkedin_stats_playwright()` |
| Session/context handling | `backend/pipeline/linkedin/outreach/session_loader.py`, `login_capture.py` |
| AI (connection note / follow-up / reply classification) | `backend/pipeline/ai/outreach_prompts.py` |
| DB models | `LinkedInAccount`, `LinkedInTarget`, `LinkedInCampaign`, `LinkedInSequenceStep`, `LinkedInMessageLog`, `LinkedInReplyClassification`, `FingerprintProfile`, `Proxy`, `ActiveLease` in `backend/models/sql_models.py` (lines 243–272, 1055–1200) |
| Debug/scratch evidence of the breakage | `backend/scripts/debug_profile_modal.py`, `debug_session_nav.py`, `inspect_profile_buttons.py`, `test_click_connect.py`, `test_js_click_connect.py`, `test_span_click_connect.py`, `test_voyager_connection_request.py`, `test_with_jsessionid.py`, `execute_guaranteed_voyager_send.py`, `real_linkedin_login_setup.py` — a dozen ad-hoc scripts that only exist because the main flow doesn't reliably work |

### Email Campaign (working)
| Layer | File |
|---|---|
| Frontend page | `Frontend/src/pages/EmailCampaign.jsx` (2,159 lines) |
| Frontend components | `Frontend/src/components/EmailBeautifyModal.jsx` |
| Backend routes | `backend/app/routes/campaigns.py` (CRUD, launch/pause/resume/duplicate, `beautify-email`, image/attachment upload), `backend/app/routes/leads.py` (import CSV/API/companies/people, resend, suppression), `backend/app/routes/tracking.py` (open pixel, click redirect, unsubscribe page, `tracker.js`), `backend/app/routes/analytics.py` (dashboard/overview/trends/per-campaign) |
| Automation engine | `backend/app/core/email_worker.py` — send scheduling, working-hours logic, lead scoring (`add_score`, `classify_score` → cold/warm/hot/sql), IMAP reply polling |
| AI (beautify email) | `backend/pipeline/ai/client.py` + prompt inline in `campaigns.py::beautify_email()` |
| DB models | `Campaign`, `Lead`, `Suppression`, `TrackingEvent`, `EmailLog` (lines 272–459) |

### Newsletter (working)
| Layer | File |
|---|---|
| Frontend page | `Frontend/src/pages/Newsletter.jsx` (1,476 lines) |
| Backend routes | `backend/app/routes/newsletters.py` — newsletter CRUD, subscriber add (manual/from companies/from people), editions (create/list/update/delete), image upload |
| Send scheduling | `backend/app/core/email_worker.py::check_scheduled_newsletters()` |
| Tracking | Reuses `TrackingEvent` (via `newsletter_id`/`subscriber_id`/`edition_id` columns) and `backend/app/routes/tracking.py` |
| DB models | `Newsletter`, `NewsletterSubscriber`, `Edition`, `NewsletterSend` (lines 760–864) |

### CRM Pipeline (working, but thin)
| Layer | File |
|---|---|
| Frontend page | `Frontend/src/pages/CRMPipeline.jsx` (148 lines — the smallest of the four; it's a **read-only Kanban board**, not an editable pipeline) |
| Backend route | `backend/app/routes/companies.py::get_pipeline_items()` (`GET /api/companies/pipeline`, lines 1134–1216) — a single endpoint that runs 6 independent queries and buckets the results into fixed columns |
| Data sources it aggregates (no dedicated pipeline table exists) | `Company` (→ "Prospects"), `Lead` filtered by status (→ "Contacted" / "In Negotiation"), `Report` (→ "Proposals Generated"), `Meeting` (→ "Meetings Booked"), `Tender` where `has_award=True` (→ "Won") |

---

## 3. Why the LinkedIn campaign is broken in PPT-Agent

This is directly documented in the code comments of `linkedin_worker.py`:

- The connection-request flow opens a browser context by **replaying only the account's cookie jar**, but the original version used a hardcoded user-agent/timezone with no proxy. LinkedIn's fraud-detection layer sees a session cookie issued under one fingerprint suddenly being used under a different one, and force-redirects the request between the profile page and an auth/checkpoint wall (`net::ERR_TOO_MANY_REDIRECTS`).
- A partial fix (`session_loader.open_authenticated_context()`) was added to replay the *full* fingerprint, but the sheer number of one-off debug/test scripts in `backend/scripts/` (12+ files with names like `test_js_click_connect.py`, `test_with_jsessionid.py`, `execute_guaranteed_voyager_send.py`) is itself evidence that the team was still fighting the problem by trial-and-error at the point this zip was captured — trying direct Voyager API calls with manually extracted `JSESSIONID` cookies as a workaround when the Playwright UI-click approach failed.
- Net effect: the send/scrape flow is fragile against LinkedIn's bot detection, not a simple bug — this is an inherent risk of the "replay a scraped cookie with a mismatched fingerprint" architecture.

**linki does not have this problem.** `lib/linkedin/session.ts` launches every context (login *and* runtime) with `playwright-extra` + `puppeteer-extra-plugin-stealth` and a single shared `contextOptions()` function, so the fingerprint used at login is guaranteed identical to the one used later — which is exactly the fix PPT-Agent was trying (and failing) to retrofit.

**Recommendation:** don't port PPT-Agent's LinkedIn engine into linki. Keep linki's `lib/linkedin/*` as the source of truth for LinkedIn automation; it's the architecturally sounder implementation of the same idea.

---

## 4. Feature-by-feature comparison

### 4.1 LinkedIn Outreach

| Feature | linki | PPT-Agent |
|---|---|---|
| Connection requests | ✅ `lib/linkedin/connect.ts`, works | ⚠️ present but unreliable (see §3) |
| Session/fingerprint handling | ✅ stealth + consistent fingerprint | ⚠️ cookie replay, fingerprint drift |
| Multi-step sequences (connect → wait → message → follow-up) | ✅ built into `Workflows` as the "linkedin" track | ✅ `LinkedInSequenceStep` model, separate campaign concept |
| Inbox / reply sync | ✅ `pending-invitations.ts`, `sync-accepted.ts` | ✅ `linkedin_inbox.py`, `poll_inbox_playwright()` |
| Profile scraping / enrichment | ✅ `profile-scrape.ts`, `enrich.ts` (Apollo) | ✅ `pipeline/linkedin/*` (much larger scraper stack — public + authenticated scrapers, business-intel extractor, data cleaner) |
| Multiple LinkedIn accounts | ✅ `accounts` table, pause/resume | ✅ `linkedin_accounts.py`, pause/resume, per-account stats |
| Proxy support | not visible in this zip | ✅ `Proxy`, `FingerprintProfile` models exist (unclear if wired up) |
| AI-personalized connection notes | ✅ per-step, multi-provider model picker | ✅ `generate_connection_note()` — single fixed model, 280-char hard cap logic |
| AI reply classification | not present | ✅ `classify_reply_intent()` |
| Working status | ✅ working | ❌ broken |

**Verdict:** linki's LinkedIn feature is already more reliable. PPT-Agent's only genuine edge here is **AI reply-intent classification** and its **deeper company/business-intel scraper** — both portable as standalone utilities without touching linki's send engine.

### 4.2 Email Campaign

| Feature | linki | PPT-Agent |
|---|---|---|
| Campaign CRUD | ✅ (as the "email" track of a Workflow) | ✅ dedicated `Campaign` model |
| Bulk send with daily limits / working hours | not present — linki sends are driven by workflow step delays, not a daily cap or business-hours gate | ✅ `is_within_working_hours()`, `daily_limit`, `get_next_working_hour()` |
| Open/click tracking (pixel + redirect) | ❌ **not present at all** | ✅ `tracking.py` — `/open/{id}.png`, `/click/{id}`, `tracker.js` |
| Unsubscribe handling | ❌ not present | ✅ `/unsubscribe/{campaignId}/{leadId}` HTML page + `Suppression` table |
| Reply detection (IMAP) | ✅ `lib/email/inbox.ts` | ✅ `check_incoming_replies()` |
| Lead scoring / grading (cold/warm/hot/SQL) | ❌ not present | ✅ `add_score()`, `classify_score()` |
| CSV import of leads | ✅ `lib/csv-import.ts`, `pages/lists/[id].tsx` | ✅ `leads.py::import/csv`, plus import from companies/people |
| Campaign analytics dashboard (charts: sent, open rate, click rate, reply rate, trends) | ⚠️ partial — `dashboard/stats.ts` has raw counts and a 7–90 day activity trend, but **no percentage-rate cards** (open/click/reply %) because there's no tracking data to compute them from | ✅ `analytics.py` — `/dashboard`, `/overview`, `/campaign/{id}`, `/trends`; frontend renders these as `recharts` bar charts + 6 summary cards |
| AI email content generation | ✅ per-step, with tone/max-words/language controls | ✅ but narrower — only email body via workflow-independent generation |
| AI "beautify" plain text → styled HTML | ❌ not present | ✅ `beautify-email` endpoint, 3 style presets, graceful fallback template if AI fails |
| Attachment support (proposal PDF, arbitrary file) | not present | ✅ upload + attach at send time |
| Working status | ✅ | ✅ |

**Verdict:** this is where linki has the biggest functional gap. Tracking, unsubscribe/suppression, lead scoring, and the beautify-email AI feature are all real, working PPT-Agent capabilities linki genuinely lacks.

### 4.3 Newsletter

| Feature | linki | PPT-Agent |
|---|---|---|
| Newsletter/list concept | ❌ not present — linki's `lists` are prospect segments for outreach, not subscriber mailing lists | ✅ `Newsletter` model, `active/paused/archived` status |
| Subscribers (manual add, bulk from companies, bulk from people) | ❌ | ✅ 3 separate add flows |
| Editions/issues (draft → scheduled → sending → sent) | ❌ | ✅ `Edition` model with full status lifecycle |
| Per-subscriber send tracking | ❌ | ✅ `NewsletterSend` (open/click per subscriber per edition) |
| Scheduled sending | ❌ | ✅ `check_scheduled_newsletters()` in the worker loop |
| Image embedding in issues | ❌ | ✅ `upload-image` / `images/{filename}` |
| Working status | n/a (doesn't exist) | ✅ |

**Verdict:** this entire feature is missing in linki. It's the most self-contained of the four to port, since it doesn't depend on the LinkedIn engine at all and only lightly depends on Email (reuses the same SMTP sender + tracking pixel).

### 4.4 CRM Pipeline

| Feature | linki | PPT-Agent |
|---|---|---|
| Kanban-style pipeline view | ❌ not present | ✅ `CRMPipeline.jsx` — 6 fixed columns |
| Dedicated pipeline/deal table | ❌ (and PPT-Agent doesn't have one either — see below) | ❌ **also absent in PPT-Agent** — it's a read-only aggregation, not a real editable pipeline |
| Drag-and-drop stage change | ❌ | ❌ — cards are click-through links to other pages, not draggable |
| Underlying data linki already has to power an equivalent view | `targets` (has `connection_requested_at`, `connected_at`, `message_sent_at`, `last_replied_at` timestamps), `runs`/`run_profiles` (workflow progress state), `lists`, `companies` | `Company`, `Lead.status`, `Report`, `Meeting`, `Tender.has_award` |

**Verdict:** PPT-Agent's "CRM Pipeline" is genuinely simple — a single aggregator endpoint plus a Kanban render component. It's a low-effort, high-visual-value port. Note it is **not** a true CRM (no stage-editing, no deal value fields beyond what `Tender` happens to have) — worth telling stakeholders that up front so expectations match what's actually being migrated.

---

## 5. AI feature comparison (all 4 areas combined)

| AI capability | linki | PPT-Agent |
|---|---|---|
| Model choice | Multi-provider picker (OpenAI, Anthropic, Google, Mistral, Qwen/Alibaba) per workflow step | Single client with an internal fallback chain (Ollama local → Gemini → OpenRouter), not user-selectable per task |
| Per-step controls | AI enable toggle, custom prompt, max-words toggle, target language, model | Fixed prompts per function, no user-facing controls |
| Connection note generation | ✅ | ✅ (280-char hard cap enforced) |
| Follow-up message generation | ✅ (as a workflow step) | ✅ `generate_followup_message()` |
| Reply intent classification | ❌ | ✅ `classify_reply_intent()` |
| Email body generation | ✅ | not a dedicated endpoint (body is user-authored, then optionally beautified) |
| Beautify plain text → HTML email | ❌ | ✅ 3 style presets + fallback template |
| Model list source | Served by an `ee/`-only route (`/api/openrouter/models`) not included in this public zip — **this route does not currently exist in the code you gave me**, so the model picker will error until that route is restored or reimplemented | N/A (not user-facing) |

**Verdict:** linki's AI architecture (per-step, multi-provider, user-controllable) is the better foundation to build on. PPT-Agent's two genuinely new capabilities — **reply intent classification** and **beautify-to-HTML** — are the pieces worth porting as new "skills" plugged into linki's existing AI client, not as a parallel AI system.

---

## 6. Summary: what to take from where

| Take from **linki** (keep as-is) | Take from **PPT-Agent** (port in) |
|---|---|
| LinkedIn automation engine (`lib/linkedin/*`) — more reliable | Newsletter feature, wholesale (schema + routes + page) |
| Unified Workflow (linkedin+email tracks) concept | CRM Pipeline aggregator + Kanban page |
| Multi-provider AI model picker | Email open/click tracking pixel + unsubscribe/suppression |
| SQLite + Next.js API routes pattern | Lead scoring/grading logic |
| Open-core (`ee/`) gating pattern, if you want to keep any of these premium | AI reply-intent classification |
| | AI beautify-email feature |
| | Working-hours-aware / daily-limit-aware send scheduling (currently missing from linki's email track) |

See `02-migration-plan.md` for exactly how to wire each of these into linki's existing TypeScript/Next.js structure.
