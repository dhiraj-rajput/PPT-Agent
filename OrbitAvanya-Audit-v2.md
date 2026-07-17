# OrbitAvanya (PPT-Agent) — Independent Codebase Audit v2

**Audited:** `PPT-Agent.zip` as uploaded (git branch `prasanna/frontend`, 5 commits ahead of `origin/prasanna/frontend`, HEAD `dcad5b2`)
**Scope:** Full repo — FastAPI backend (`api/`, `server.py`), React/Vite frontend (`Frontend/orbitavanya`), research pipeline (`linkedin/`, `website/`, `google_search/`, `orchestrator/`, `models/`), document generation (`utils/`, `bidforge/`, `scripts/`), SAM.gov integration (`api/sam_gov/`), tests, config, git history/index.
**Not re-audited:** the file you uploaded named `OrbitAvanya-Codebase-Audit.md` — that file contains only the *prompt template* used to commission the earlier audit, not its findings or your fix list. I don't have the earlier report itself, so I can't diff "fixed vs not fixed." Everything below is a fresh pass, and I've flagged which items look brand-new versus things a first-pass audit would typically already have caught.

---

## 0. Honesty about coverage

247 tracked files, ~24,000 lines of Python (excl. tests) + ~9,150 lines of JSX just in the largest 10 page components, 30 PDFs, 4 DOCX, a 7.6 MB CSV. I read every route file, every config/auth/db file, every test file's scope, the git index, and sampled the largest/most central modules in each subsystem (`linkedin/`, `website/`, `orchestrator/`, `models/`, `bidforge/`, `ai/`). I did **not** line-by-line read all 100 Python files or all 37 JSX files — for a codebase this size that would mean either shallow coverage of everything or real coverage of a subset. I chose real coverage of a subset and I'm telling you which subset. Treat the findings below as verified, not the absence of other findings elsewhere.

---

## 1. Executive summary

The backend has clearly had real security attention already: bcrypt with cost 12, OTP-gated login with attempt limits, no email-enumeration leak on forgot-password, a hard startup failure if `JWT_SECRET` is missing or weak, path-traversal guards on file downloads, subprocess calls built as argument lists (no shell injection surface), and a properly user-scoped WebSocket + task-status pattern in `proposals.py`. That's a genuinely competent baseline — better than a lot of student SaaS projects I'd expect to see at this stage.

What I found this pass, roughly in order of how much it matters:

1. **A live, populated `.env` with real credentials was included in the zip you uploaded** (Mongo URI, JWT secret, SMTP password, a LinkedIn `li_at` session cookie, and API keys for Tavily/Gemini/OpenRouter/SerpAPI/Firecrawl, plus Zoom/Google OAuth secrets). This isn't a code bug, it's an operational one — see §2.
2. **A whole duplicate copy of the repo (`PPT-Agent-bidforge-integration/`) is still tracked in git**, deleted from your working tree but not committed as deleted — anyone who clones or pulls gets it back.
3. **An IDOR-shaped gap**: the RFP Auto-Respond feature's task status/download endpoints check *that you're logged in* but not *that it's your task* — while the sibling `proposals.py` feature does this correctly. Same pattern, inconsistently applied.
4. **The entire FastAPI backend runs blocking, synchronous MongoDB calls inside `async def` route handlers**, which stalls the event loop under concurrent load — and `motor` (the async Mongo driver) is a listed dependency that is used precisely nowhere.
5. **Two dead/mismatched config keys**: `JWT_EXPIRES_IN` and `OTP_LENGTH` are documented in `.env`/`.env.example` and do nothing — the real fields are `JWT_EXPIRES_DAYS` and a hardcoded 6-digit OTP.
6. **A fabricated relevance score is persisted as if it were real**: SAM.gov company "match scores" are `random.randint(70, 98)` seeded by UEI, stored in Mongo, and presumably surfaced to users as a genuine metric.
7. **Zero automated tests for the FastAPI backend** (11 route files, ~3,600 lines, all of auth/JWT/OTP/CRM/tenders/proposals) and **zero frontend tests**, despite 2,361 lines of unit tests existing for the research-pipeline layer. No CI, no Dockerfile.

None of this is catastrophic — there's no RCE, no SQL/NoSQL injection I could find, no obviously exploitable auth bypass. It's the kind of gap list you'd expect from a project that's had one security pass focused on the auth core and hasn't yet had a pass focused on cross-feature consistency, dependency hygiene, and git hygiene. That's exactly what this pass adds.

---

## 2. New — Operational: your uploaded archive contains live secrets

`PPT-Agent/.env` (not tracked by git — good) is fully populated, not templated. Field name + value length (values never reproduced below):

| Key | Looks like |
|---|---|
| `MONGO_URI` | populated connection string (42 chars) |
| `JWT_SECRET` | populated (46 chars) |
| `LINKEDIN_LI_AT` | populated LinkedIn session cookie (153 chars) — this is a live authenticated-session token |
| `TAVILY_API_KEY`, `SAM_GOV_API_KEY`, `SERPAPI_API_KEY`, `FIRECRAWL_API_KEY`, `OLLAMA_API_KEY`, `GEMINI_API_KEY`, `OPENROUTER_API_KEY` | all populated |
| `SMTP_USER` / `SMTP_PASS` | populated mailbox credentials |
| `ZOOM_CLIENT_SECRET`, `GOOGLE_CLIENT_SECRET` | populated |

This is good news/bad news. Good: `.gitignore` correctly excludes `.env`, `/private/`, `/output/`, `/downloads/`, and `git ls-files` confirms none of them are actually tracked in git — so this isn't in your git history. Bad: the zip you hand to any external tool (including this conversation) carries all of it in the clear. My recommendation, independent of anything else in this report:

- Rotate the LinkedIn `li_at` cookie, SMTP password, and any API keys that were in this file, since they've now left your machine via this upload.
- Going forward, zip the repo with `.env`, `/private/`, and `/output/` excluded (`git archive HEAD` would do this automatically, since those paths aren't tracked) before handing it to any third party, reviewer, or AI tool.
- `/private/` also contains a real client proposal (`WK T360 Proposal - September 11, 2024.docx/.pdf`) and a 7.6 MB `sam_entities.csv` — fine that it's gitignored, but worth the same "don't zip it for third parties" discipline.

---

## 3. New — Git hygiene: a duplicate repo is still tracked

```
$ git status --porcelain | grep PPT-Agent-bidforge-integration
 D PPT-Agent-bidforge-integration/Frontend/orbitavanya/src/App.jsx
 D PPT-Agent-bidforge-integration/Frontend/orbitavanya/src/components/layout/Sidebar.jsx
 D PPT-Agent-bidforge-integration/Frontend/orbitavanya/src/pages/BidForgeUpload.jsx
 D PPT-Agent-bidforge-integration/api/routes/bidforge.py
 D PPT-Agent-bidforge-integration/bidforge/__init__.py
 ... (14 files total)
```

This is a leftover from an old merge (`Merge Frontend2.0: auth system, tasks, meetings, notifications, new pages` / `Integrate Frontend2.0 + Port auth/tasks/meetings to FastAPI + Add RFP Auto-Respond` in the log) that accidentally nested a second copy of the project under `PPT-Agent-bidforge-integration/`. You (or someone) already deleted it from disk — it doesn't exist in the working tree — but that deletion was never committed. Two consequences:

- **It's still baked into git history** on every commit before the deletion is committed, permanently, for anyone who clones the repo or checks out an old commit.
- **It will silently come back** the moment anyone runs `git stash`, `git checkout .`, or clones fresh — the index still says these 14 files should exist.

Fix: `git add -A && git commit -m "chore: remove stray PPT-Agent-bidforge-integration duplicate directory"`. (History rewriting to purge it from *past* commits too is possible via `git filter-repo`, but only worth it if something in there was sensitive — it looks like pure code, so I wouldn't bother rewriting shared history over it.)

---

## 4. New — Security findings

| # | Severity | Issue | Where | Evidence |
|---|---|---|---|---|
| 4.1 | **High** | IDOR: RFP Auto-Respond task status/download has no per-user ownership check | `api/routes/rfp_respond.py:170-188`, `utils/db_client.py:216-254` | `get_status`/`download_result` only require *a* valid JWT (`Depends(get_current_user)`); `update_task_status()` is never called with a `userId`. Any authenticated account that learns/guesses a `task_id` (12 hex chars, 48-bit) or output filename can poll another user's pipeline progress or download their generated proposal from someone else's uploaded RFP. Contrast with `api/routes/proposals.py:360-401`, which correctly scopes tasks by `user_id` and closes the WebSocket if the token doesn't resolve to a user — so the correct pattern exists in the codebase, it's just not applied here. |
| 4.2 | **Medium** | OAuth `state` param is an unsigned, unvalidated user ID | `api/routes/integrations.py:56, 84, 129-138` | `flow.authorization_url(..., state=user_id)` sends the raw user ID as `state`; `google_callback` accepts `state` from the query string and uses it directly to decide which account's Mongo `integrations` doc to upsert, with no comparison against a server-stored nonce tied to the session that initiated the flow. An attacker who can obtain a valid Google OAuth `code` (e.g., by starting their own consent flow) and knows or guesses a victim's Mongo ObjectId could call `/api/integrations/google/callback?code=<their code>&state=<victim id>` directly and link their own Google Calendar credentials to the victim's account. Fix: generate a random nonce server-side at `/google/auth-url` time, store it (e.g., in the `integrations` doc or a short-lived Mongo/Redis entry) keyed to the authenticated user, and verify it matches on callback instead of trusting `state` at face value. |
| 4.3 | **Medium** | JWT stored in `localStorage`, not an httpOnly cookie | `Frontend/orbitavanya/src/lib/api.jsx:21,59`, `src/context/AuthContext.jsx:12-30` | Any XSS anywhere in the SPA (including a future third-party script or dependency) can read the token directly via `localStorage.getItem`. Combined with a 7-day default expiry (`JWT_EXPIRES_DAYS=7`), a stolen token is a week of account access. No `dangerouslySetInnerHTML` was found in the codebase today (checked), so there's no current XSS vector I could confirm — this is a defense-in-depth gap, not a demonstrated exploit. Moving to an httpOnly/Secure/SameSite cookie removes the class of risk but requires adding CSRF protection in exchange (e.g., double-submit cookie or `SameSite=Strict` if the frontend and API can share a registrable domain).
| 4.4 | **Low** | Two documented env vars silently do nothing | `.env:79` (`JWT_EXPIRES_IN=7d`), `.env.example:79`; `.env` `OTP_LENGTH` | `config/settings.py` defines `JWT_EXPIRES_DAYS` (int), not `JWT_EXPIRES_IN` — with `extra="ignore"` in `SettingsConfigDict`, the `.env` value is silently dropped and the JWT lifetime is *always* the hardcoded 7-day default no matter what's set. `OTP_LENGTH` has no matching field at all — OTPs are hardcoded to 6 digits in `_generate_otp()` (`api/routes/auth.py:85-86`). Neither will error, they'll just be ignored, which is the quietly-dangerous kind of bug. |
| 4.5 | **Low** | Health endpoint can leak internal exception text | `server.py:110-126` | `db_status = f"unhealthy: {e}"` returned unauthenticated on `/api/health`. In most misconfiguration cases this exception string is a generic pymongo timeout, but if it ever includes connection details (some pymongo error paths echo back parts of the URI or hostname) that leaks to an unauthenticated caller. Cheap fix: log the exception, return a generic `"unhealthy"` string in the response body. |
| 4.6 | **Info** | LinkedIn scraping (authenticated + public) is a documented business/compliance risk, not a code bug | `linkedin/authenticated_scraper.py`, `linkedin/GUIDE.md` | Scraping LinkedIn via a session cookie is against LinkedIn's Terms of Service regardless of how carefully rate-limited it is (and this project does rate-limit thoughtfully — `SCRAPE_DELAY_MIN/MAX_SECONDS`, `BROWSER_HEADLESS`). Worth a one-line risk-acceptance note in the README for anyone else who joins the project, since it's not obvious from the code that this is a known, accepted trade-off rather than an oversight. |

**Not found (checked and clean):** SQL injection surface (no raw SQL anywhere — MongoDB only, and I didn't find string-interpolated queries), `eval`/`exec` usage, shell-injection via `subprocess` (all calls use list-form `Popen`/`run`, no `shell=True`), bare `except:` clauses, hardcoded credentials in source (only in the gitignored `.env`), path traversal on file downloads (both `rfp_respond.py` and the download routes I checked use `Path(name).name` correctly).

---

## 5. New — Performance: the async/sync mismatch

`requirements.txt` lists `motor>=3.6.0` (the async MongoDB driver) as a dependency, and the module docstring in `utils/db_client.py` and README both frame MongoDB access as a considered architectural choice. In practice:

```
$ grep -rn "motor\|AsyncIOMotorClient" --include="*.py" .
(no results)
```

Zero usages. Every single database call in the codebase goes through `pymongo.MongoClient` — a **synchronous, blocking** driver — including calls made directly inside `async def` route handlers (e.g. `api/routes/companies.py`, `api/routes/tenders.py`, `api/routes/auth.py` all call `get_collection(...).find_one(...)` etc. straight from `async def` functions). FastAPI does not auto-thread the body of an `async def` route the way it does for plain `def` routes — if you block inside `async def`, you block the single-threaded event loop for every concurrent request. Under load, this means one slow Mongo query serializes all other in-flight requests, negating most of the benefit of choosing an async framework in the first place.

Two honest fixes, not both required:
- **Cheapest**: change routes that only do blocking I/O (most of them) from `async def` to plain `def`. FastAPI will then run them in its threadpool automatically, which is what you actually want here.
- **More correct long-term**: adopt `motor`'s `AsyncIOMotorClient` for real async I/O and drop the unused sync dependency — bigger refactor, but it's the dependency you already pay for and aren't using.

Either way, `motor` should come out of `requirements.txt` if you go with the cheap fix, since a listed-but-unused dependency is itself a small maintenance/audit-noise cost.

---

## 6. New — A fabricated metric is stored as if it were real data

`api/routes/companies.py:15-55` (`import_sam_entities_csv`), the function that seeds the `companies` Mongo collection from `private/sam_entities.csv` on first boot:

```python
random.seed(uei)
match_score = random.randint(70, 98)
```

This produces a deterministic-per-UEI but otherwise meaningless number in the 70–98 range and stores it on every company document as `match_score`. It's deterministic (same UEI always gets the same number) so it *looks* stable and computed, but it isn't derived from anything about the company, the opportunity, or the user's business — it's a seeded random number. If this value is ever rendered in the frontend as a "match %" or similar (worth checking `Frontend/orbitavanya/src/pages/Companies.jsx` and `CompanyDetail.jsx`, which I didn't trace end-to-end), users would reasonably read it as a real relevance signal and make prioritization decisions off a coin flip. Either compute a real score (e.g., NAICS/keyword overlap with the user's SAM.gov profile, historical win-rate, geographic match) or don't persist a field named `match_score` at all — a fabricated-but-stable number is worse than no number, because it's indistinguishable from a real one at the UI layer.

---

## 7. Cross-file validation: the same feature, two different quality bars

Because the `task_statuses` collection and `Depends(get_current_user)` pattern are shared infrastructure, I compared how the two features that use them ("AI Proposal Generation" and "RFP Auto-Respond") each apply it:

| | `api/routes/proposals.py` | `api/routes/rfp_respond.py` |
|---|---|---|
| Task keyed by | `user_id` + company (`get_user_proposal_tasks_dict(user_id)`) | raw `task_id` only |
| WebSocket auth | decodes token, closes 1008 on failure, scopes pushed state to `user_id` | no WebSocket |
| Status endpoint ownership check | ✅ implicit via user-scoped dict | ❌ any authenticated user can query any `task_id` |
| Download ownership check | N/A (no download route) | ❌ any authenticated user can download any filename that exists on disk |

This is exactly the kind of thing Phase 4 cross-file validation is meant to catch and a single-file review would miss: neither file is "wrong" in isolation, but the inconsistency means the security property you actually shipped for one feature silently doesn't hold for its sibling. Worth checking whether any other route pairs sharing `utils/db_client.py` helpers have the same asymmetry — I didn't have time to check `tasks.py`/`meetings.py`/`notifications.py` against each other with the same rigor.

---

## 8. Testing & CI/CD — the gap is the backend, not the whole project

```
tests/unit/test_compactor.py              56
tests/unit/test_browser_scraper.py       112
tests/unit/test_rfp_pipeline.py          132
tests/unit/test_helpers.py               188
tests/performance/test_cleaner_performance.py 194
tests/unit/test_normalizer.py            194
tests/unit/test_orchestrator_and_website.py 232
tests/unit/test_storage.py               312
tests/unit/test_models.py                388
tests/unit/test_data_cleaner.py          538
                                    total 2,361 lines
```

That's real coverage of the research-pipeline layer (LinkedIn/website scraping, data cleaning, normalization, the orchestrator). But:

- **0 tests** touch `api/routes/*` — the 11 files, ~3,600 lines that are the entire product surface a user or attacker actually interacts with (auth, OTP, JWT, tasks, meetings, notifications, integrations, companies, tenders, proposals, RFP respond).
- **0 tests** for `utils/db_client.py`, `config/settings.py`, `server.py`.
- **0 frontend tests** — no `*.test.jsx`/`*.spec.jsx` anywhere under `Frontend/`, despite ~9,150 lines just in the ten largest page components.
- **No CI config** anywhere (`find . -iname "*.yml" -o -iname "*.yaml"` returns nothing outside `node_modules`) — nothing runs the existing 2,361 lines of tests automatically on push/PR today.
- **No Dockerfile / docker-compose** — deployment today is "clone, `pip install`, `bun install`, run two processes by hand," which is fine for a solo dev loop and not fine the moment a second person or a staging server enters the picture.

If I were prioritizing one testing investment, it would be `api/routes/auth.py` and `api/routes/rfp_respond.py`/`proposals.py` first — auth because it's the highest blast-radius code in the repo, and the task-ownership pair because §7 shows exactly the kind of regression a test would have caught.

---

## 9. Code quality — cohesion

Largest files by line count (not automatically bad, but worth a look for split-out opportunities):

| File | Lines |
|---|---|
| `utils/rfp_response_generator.py` | 1,038 |
| `api/routes/tenders.py` | 990 |
| `orchestrator/nodes.py` | 979 |
| `api/sam_gov/opportunities.py` | 733 |
| `linkedin/data_cleaner.py` | 756 |
| `website/crawler.py` | 673 |
| `models/compactor.py` | 653 |
| `Frontend/.../pages/AIResearch.jsx` | 803 |
| `Frontend/.../pages/CompanyDetail.jsx` | 667 |
| `Frontend/.../pages/Companies.jsx` | 624 |

`tenders.py` at 990 lines with 7 endpoints averages ~140 lines/endpoint, which usually means either genuinely complex SAM.gov business logic (plausible, given the domain) or helper functions that belong in `api/sam_gov/` alongside `opportunities.py` rather than in the route file. `AIResearch.jsx` at 803 lines in a single React component is the more clear-cut case — that's very likely multiple components (search form, results list, detail panel, filters) that got built inline and would benefit from extraction, both for readability and for the frontend test suite you don't have yet to have something testable to target.

Other code-quality notes, all minor:
- 21 backend files use `print()` for operational logging despite `utils/helpers.setup_logger()` existing and being used elsewhere (e.g. `db_client.py`) — inconsistent, makes log levels/filtering unreliable in production.
- 3 `TODO`/`FIXME` markers total — genuinely low for a codebase this size, which is a positive signal, not a negative one.
- 0 bare `except:` and 0 `except Exception: pass` patterns found — exceptions are consistently either logged or re-raised. Good discipline.
- `requirements.txt` pins **zero** exact versions — every entry is `>=`, including `langgraph>=0.2.0` and `crawl4ai>=0.4.0`, both fast-moving pre-1.0-feeling packages where a minor bump can change behavior under you. Recommend `pip freeze > requirements.lock.txt` (or migrate to `pyproject.toml` + `uv`/`poetry` lockfile) for reproducible installs, keeping the loose `requirements.txt` as the human-editable source if you like.
- README says `bun install # or npm install`, but only `bun.lock` exists in the repo (the previously-tracked `package-lock.json` shows as deleted in `git status`, unresolved) — an `npm install` today won't be reproducible. Either commit to bun-only in the README or regenerate and commit `package-lock.json`.

---

## 10. What's already solid (worth keeping, not re-litigating)

- Password hashing: bcrypt, cost factor 12, correct.
- OTP flow: SHA-256 hashed at rest, 5-attempt limit, TTL-expired via Mongo `expireAfterSeconds` index, no email enumeration on forgot-password.
- `JWT_SECRET` hard-fails app startup if missing or left at the placeholder value (`api/utils/auth.py:30-31`) — this is the right failure mode (loud and early, not silent).
- Mongo URI is redacted before being logged (`utils/db_client.py:57-58`).
- File upload paths are sanitized (`_safe_name` in `rfp_respond.py`) and download paths use `Path(name).name` to block traversal.
- Subprocess invocation for the BidForge/RFP pipeline uses list-form args (no shell injection) and is concurrency-limited via `SUBPROCESS_SEMAPHORE`.
- `.gitignore` correctly excludes `.env`, `/private/`, `/output/`, `/downloads/` — and I verified none of them are actually tracked in git history despite existing on disk.
- Sensible index creation on startup (`ensure_all_indexes`), including a TTL index for OTPs and task statuses so those collections self-clean.

---

## 11. Priority action list

| Priority | Item | Effort |
|---|---|---|
| Do now | Rotate credentials that were in the uploaded `.env` (LinkedIn cookie, SMTP password, API keys) | ~30 min |
| Do now | `git add -A && git commit` the `PPT-Agent-bidforge-integration` deletion | 5 min |
| High | Add `userId` ownership check to `rfp_respond.py` status/download endpoints (mirror `proposals.py`'s pattern) | 1–2 hrs |
| High | Sign/validate the OAuth `state` param in `integrations.py` | 1–2 hrs |
| High | Fix `JWT_EXPIRES_IN` → `JWT_EXPIRES_DAYS` mismatch in `.env`/`.env.example`; either wire up `OTP_LENGTH` or delete it from the example file | 15 min |
| High | Decide: real `match_score` computation, or remove the field | 1 hr (remove) to 1 day+ (real scoring) |
| Medium | Convert blocking-only `async def` routes to plain `def`, or migrate to `motor`; drop `motor` from requirements if not adopted | 2–4 hrs (quick fix) |
| Medium | First test pass on `api/routes/auth.py` + the task-ownership pair (`proposals.py`/`rfp_respond.py`) | 1–2 days |
| Medium | Add a minimal CI workflow (lint + existing 2,361 lines of tests) on push/PR | 2–3 hrs |
| Low | Pin dependency versions (backend lockfile + resolve npm/bun README mismatch) | 1–2 hrs |
| Low | Split `AIResearch.jsx` and `tenders.py` into smaller units | 1–2 days each, non-urgent |
| Low | Route `print()` calls through `setup_logger` | 1–2 hrs |
| Low | Generic error body on `/api/health` instead of raw exception text | 10 min |

---

## 12. What I'd audit next if you want a second pass

- `orchestrator/graph.py`/`nodes.py` and `models/compactor.py` for actual LLM-output handling correctness (JSON schema drift, retry/fallback behavior under real 429s) — I read the AI client's retry/fallback design and it's sound, but didn't trace every call site.
- `linkedin/` and `website/` scraper internals for resilience against site markup changes — these are inherently brittle by nature of scraping, worth knowing your specific failure modes.
- The other 9 route files' authorization matrices at the same granularity I did for `proposals.py`/`rfp_respond.py`/`integrations.py` (I sampled; I didn't do all 11 endpoint-by-endpoint).
- Frontend component-level XSS/data-handling review beyond the `dangerouslySetInnerHTML` grep (clean today, but worth checking anywhere user-controlled RFP/company text gets rendered).

---
---

# PART 2 — Second Pass (full-codebase follow-up)

Scope this pass: all 11 route files read in full (not sampled), `api/sam_gov/` (all 5 files), `api/utils/mailer.py` and `video_rooms.py` in full, `orchestrator/graph.py` in full + `nodes.py` structurally, `ai/mode.py` in full, `models/compactor.py`'s JSON-parsing path, `utils/helpers.py`'s concurrency primitives, `utils/rfp_parser.py` structurally, `main.py` in full, and — the big gap from Part 1 — **all 37 frontend files surveyed, with the 9 largest pages read directly**. Repo-wide greps for pickle/unsafe-yaml/eval/missing-timeouts/hardcoded-URLs were run across every file, not sampled.

Still not read line-by-line: `linkedin/*` (13 files) and `website/*` (9 files) beyond structural survey + grep sweeps — these are internal scraping tooling with their own 2,361-line test suite already, so they carried the lowest incremental risk per hour spent versus the areas above. If you want, a third pass can go through those two directories the same way this pass went through the API and frontend.

## 13. The single most important finding: most of the frontend can't authenticate to the backend

`Frontend/orbitavanya/src/lib/api.jsx` is the intended single access point — `_request()` correctly reads the JWT from `localStorage` and attaches `Authorization: Bearer <token>` to every call. But eight page/component files don't go through it. They call the browser's `fetch()` directly, against a hardcoded URL, with no auth header at all:

| File | Raw unauthenticated `fetch()`/`href` calls |
|---|---|
| `pages/CompanyDetail.jsx` | 7 |
| `pages/AIResearch.jsx` | 6 |
| `pages/ProposalBuilder.jsx` | 4 |
| `pages/Reports.jsx` | 1 fetch + 3 `href`/`src` (list at §14) |
| `pages/TenderDetail.jsx` | 3 |
| `pages/Tenders.jsx` | 3 |
| `pages/Companies.jsx` | 3 |
| `components/layout/Topbar.jsx` | 2 |

Example, `Companies.jsx:90` (adding a company manually — a write, not just a read):
```js
fetch('http://localhost:5050/api/companies', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(manualForm)
})
```
No `Authorization` header. Every one of the backend routes these 29 calls target — `/api/companies*`, `/api/proposals*`, `/api/tenders*`, `/api/reports` — requires `Depends(get_current_user)` (verified in Part 1 and re-confirmed this pass). `get_current_user` raises `401` when no `credentials` are supplied at all (`api/utils/auth.py:88-89`). I checked for a global fetch interceptor that might inject the header some other way (`main.jsx`, a `window.fetch` override) — there isn't one.

**Net effect: as currently committed, the Companies list/detail, AI Research, Proposal Builder, Tenders list/detail, and Reports pages — the actual core product — cannot successfully call the backend.** Every request from these pages gets a `401` and (based on how each page handles errors) either shows an error toast, an empty state, or a broken load spinner, depending on the page.

This isn't a security bug (if anything the backend is correctly *rejecting* unauthenticated requests) — it's a functional regression, and the shape of it tells you exactly how it happened: `api.jsx`'s own docstring says "ALL routes... point to the single FastAPI backend," and the git log shows JWT auth was ported in later (`7b94e8d feat: Integrate Frontend2.0 + Port auth/tasks/meetings to FastAPI...`) on top of pages that were originally written against an unauthenticated or differently-authenticated backend. The pages that were written or touched as part of that auth port (Tasks, Meetings, Notifications, Users, Settings, RFP Auto-Respond's upload/status calls) correctly use `api.js` and work. The pages that predate it were never migrated.

**This is the top priority fix in this entire report.** It's also mechanical and low-risk to fix: replace each hardcoded `fetch('http://localhost:5050/...')` call with the equivalent `api.*` method (adding new methods to `api.jsx` for the handful of endpoints — company research status, AI mode, tender sync/meta, draft-requests, etc. — that don't have one yet). I'd estimate this is a 3–6 hour mechanical pass across 8 files, plus manual click-through testing of each affected page afterward.

## 14. Downloads and previews are broken by construction, even where auth isn't the issue

Three places in `Reports.jsx` and one in `RFPAutoRespond.jsx` render a plain `<a href={url} download>` (or `<iframe src={url}>`) pointing straight at an authenticated backend route:

```jsx
// Reports.jsx:133, 186, 208
href={`http://localhost:5050/api/reports/download/${r.filename}`}
// Reports.jsx:195
src={`http://localhost:5050/api/reports/view/${previewing.filename}`}
// RFPAutoRespond.jsx:324
<a href={downloadUrl} download>Download Proposal</a>
```

Browsers do not attach `Authorization` headers to plain navigations or `<iframe>` loads — only to `fetch`/`XHR` calls where the JS explicitly sets the header. All four target routes (`api/routes/reports.py:152,161`; `api/routes/rfp_respond.py:178`) require `Depends(get_current_user)`. Clicking any of these buttons, or opening the report preview modal, will hit a 401 instead of the file. This is on top of the hardcoded-localhost issue in §15 — even once that's fixed, these specific links will still 401 unless changed.

Standard SPA fix: fetch the file via `api.js` (so the Bearer header goes along), get it as a `Blob`, then trigger the download with `URL.createObjectURL(blob)` + a temporary `<a>` click — or, less ideally, switch these specific download/view/preview endpoints to accept a short-lived signed token as a query parameter instead of requiring the header (acceptable for downloads specifically, with the usual caveat that a token in a URL can end up in server access logs, so make it single-use and short-lived if you go this route).

## 15. Hardcoded `http://localhost:5050` appears 44 times across 9 files — blocks any real deployment

```
Topbar.jsx            2
lib/api.jsx            2   ← fine, this is the documented fallback default
CompanyDetail.jsx     11
TenderDetail.jsx       5
Tenders.jsx             3
AIResearch.jsx          7
Reports.jsx             5
ProposalBuilder.jsx     6
Companies.jsx           3
```

`api.jsx`'s two occurrences are legitimate — one in a docstring, one as `import.meta.env.VITE_API_URL || 'http://localhost:5050'`, i.e. the intended dev fallback. The other 42, across 8 files, are literal strings baked into `fetch()` calls and `href`/`src` attributes. This means: even after fixing the auth-header problem in §13, none of these calls would work anywhere except a machine with the backend running on `localhost:5050` specifically. Deploying the frontend to any staging/production host — where the backend lives at a real domain — would leave these 8 pages silently trying (and failing, likely as CORS/connection errors from a deployed frontend trying to reach a browser-local port) to reach `localhost:5050` on the *visitor's own machine*, not your server.

Same fix as §13 covers this too, since routing these calls through `api.js`'s `BASE_URL` (which already correctly reads `VITE_API_URL`) fixes both problems in the same pass.

## 16. New backend findings

| # | Severity | Issue | Where | Evidence |
|---|---|---|---|---|
| 16.1 | **High** | Meeting invite/cancellation emails always fail — `NameError` on every call | `api/utils/mailer.py:256,283` | `send_meeting_invite_email` and `send_meeting_cancelled_email` both call `_subject_safe(title)` in an f-string — `_subject_safe` is never defined anywhere in the 283-line file (confirmed via full-file grep). This raises `NameError` on every single meeting creation or cancellation with attendees. It doesn't crash the request, because both call sites in `meetings.py` use `asyncio.gather(..., return_exceptions=True)`/fire-and-forget — so the failure is completely silent from the user's perspective except that `inviteSent` gets set to `False` on meeting creation, and cancellation emails just never go out with no trace at all. Fix: replace `_subject_safe(title)` with e.g. `title.replace("\n", " ")[:120]` (or just drop the wrapper and use `title` directly — email subject headers don't need HTML escaping, only the body does, and that's already handled separately by `_e()`). |
| 16.2 | **High** | `/api/companies/settings/ai-mode` is unauthenticated-by-role and mutates a file on disk at runtime | `api/routes/companies.py:457-483` | Only `Depends(get_current_user)` (any Team Member), not `Depends(require_admin)` — yet this endpoint flips a master switch controlling whether every AI-powered feature in the app calls paid LLM APIs or falls back to rules. It also does `env_path.write_text(...)` to literally rewrite the `.env` file's `AI_MODE=` line on every call. Two problems compound: (a) any team member can change org-wide behavior/cost without elevated privilege, and (b) in any multi-worker deployment (the standard way to run FastAPI in production — see §16.5), this only updates the in-memory `settings.AI_MODE` of the one worker that handled the request, while the file write is what future restarts pick up — so a fleet of workers can silently disagree with each other about which mode they're in. Fix: gate behind `require_admin`; store the setting in Mongo (a `settings` collection) instead of rewriting `.env`, so every worker reads the same source of truth. |
| 16.3 | **Medium** | `/api/companies/import` (JSON format) inserts arbitrary user-supplied dicts into MongoDB with no schema | `api/routes/companies.py:213-220` | `items = json.loads(raw_data); ...; col.insert_one(item)` — `item` is whatever the caller sent, inserted as-is. Contrast with the single-company `POST /api/companies`, which validates against the `CompanyCreateBody` Pydantic model (a whitelist). Any authenticated Team Member can insert documents with arbitrary shape/fields into the `companies` collection via this path, which can corrupt data the frontend assumes has a fixed shape, or insert oversized documents (no size cap). Fix: validate each imported item against `CompanyCreateBody` (or a dedicated import schema) the same way the single-add endpoint does. |
| 16.4 | **Medium** | No app-level cooldown on `/api/tenders/sync`, which spends a shared, very small daily quota | `api/routes/tenders.py:447-470` | The docstring itself documents that the free SAM.gov tier allows **10 requests/day total for the whole org**. The endpoint is callable by any authenticated user with no rate limit or last-synced check, so a few accidental double-clicks (there's no client-side disable-while-loading guard I could confirm either) can exhaust the day's quota for everyone. Fix: store `last_synced_at` and reject (with a clear message) syncs within some cooldown window, or require `require_admin` for manual syncs and drive routine syncing from a scheduled job instead. |
| 16.5 | **Low** | `SUBPROCESS_SEMAPHORE` is a process-local `threading.Semaphore(3)`, not shared across workers | `utils/helpers.py:34` | Hardcoded (not configurable via `config/settings.py`), and scoped to a single Python process. This is fine for `python server.py` (one process) but silently stops providing the intended "max 3 concurrent heavy subprocess pipelines" protection the moment the app is run with multiple workers (`uvicorn server:app --workers 4`), which is the standard way to deploy a FastAPI app in production — the real ceiling becomes `3 × worker_count` with no single place that knows the true total. Fix: back it with a Mongo- or Redis-backed counter if the app will ever run multi-worker (which it should, for a "SaaS" positioned this way). |
| 16.6 | **Low** | No file-size or PDF-page-count ceiling on RFP uploads | `api/routes/rfp_respond.py:134-152`, `utils/rfp_parser.py` | `f.write(await file.read())` loads the entire uploaded file into memory before writing it, with no size check anywhere in the request path (confirmed no `Content-Length`/`MAX_UPLOAD` check exists anywhere in the codebase). Downstream OCR (`utils/rfp_parser.py`) iterates `reader.pages` with no page-count cap. A large or adversarial PDF can drive high memory and CPU use through a single request. Fix: reject uploads over a configured size before reading the body fully (check `Content-Length`, or stream to disk with a running byte counter and abort past the limit); cap OCR to the first N pages with a clear "truncated" note in the output. |
| 16.7 | **Low** | The fabricated `matchScore` pattern is more widespread than Part 1 showed, and one instance documents it as intentional | `api/routes/companies.py:33,77,198,240`; `api/routes/tenders.py:49-52` | Four separate insertion paths now confirmed: the CSV importer (`random.seed(uei)`), the manual single-add endpoint (same fallback), the bulk `/import` CSV path (hardcoded default `82` if not supplied), and tenders' own `_compute_match_score()` (`random.seed(notice_id)`, docstring: *"Deterministic match score (70-98) seeded on noticeId — stable across restarts"*) — so this is a deliberate design choice, not leftover scaffolding. Doesn't change the recommendation from Part 1: before this ships, either replace it with a real signal or rename/relabel the field so it doesn't read as a computed relevance score to end users. Related: the CSV importer also silently inserts the placeholder `info@company.com` when a company record has no contact email (`companies.py:243`) — same "fabricated-looking-real" pattern, smaller stakes. |
| 16.8 | **Low** | `requester` on RFP draft requests defaults to a hardcoded name, not the logged-in user | `api/routes/tenders.py:862` | `"requester": payload.get("requester", "John Doe")` — the endpoint already has `current_user` available via `Depends(get_current_user)` and doesn't use it here. If the frontend doesn't always pass `requester` explicitly, every draft request in the CRM shows "John Doe" regardless of who clicked it, undermining the field's purpose. Fix: default to `current_user.get("name")` instead of a hardcoded string. |
| 16.9 | **Low** | Progress bars are driven by matching substrings in subprocess stdout, not structured events | `api/routes/rfp_respond.py:86-99`, `api/routes/companies.py:301-314` | Both background-subprocess flows update UI progress by checking things like `"Step 1" in line` or `"classify_input" in line` against raw `print`/log output from `main.py`/`bidforge_cli.py`. This works today but is a silent coupling: renaming a log message or a node function in `orchestrator/nodes.py` breaks the corresponding progress bar with no error anywhere — it'll just stop advancing past whatever percentage it last matched. Not urgent, but worth a comment at each end pointing to the other, or better, replacing string-matching with the subprocess calling `update_task_status()` directly (it already imports from the same `utils.db_client` module the parent process uses). |

## 17. Confirmed clean / additional positive findings this pass

- `ai/mode.py`'s AI/rule-based fallback dispatcher (`run_with_fallback`) is cleanly designed: per-agent override resolution, explicit `RateLimitError` vs `AIUnavailableError` vs generic-exception handling, all logged distinctly. No bugs found.
- `models/compactor.py`'s `_parse_json_from_response()` has a solid three-stage fallback for LLM output (fence-stripping → direct parse → regex-extracted-object parse) with clear `ValueError`s on total failure rather than swallowing or returning garbage.
- Repo-wide grep for `requests.get/post`/`httpx.get/post/Client` calls without an explicit `timeout=` came back with only false positives (multi-line calls that do set timeout further down) — every outbound HTTP call I could find sets an explicit timeout. No unbounded-hang risk from third-party API calls.
- No `pickle` usage, no unsafe `yaml.load` anywhere in the codebase.
- `api/utils/mailer.py` has a deliberate, documented `_e()` HTML-escaping helper applied to every piece of user-controlled content (task titles, meeting titles/locations, names) before it goes into an email body — with a docstring explicitly explaining *why*, which is the kind of thing you only see when someone already thought about this failure mode. Genuinely good practice, undermined only by the unrelated `_subject_safe` bug in §16.1.
- `notifications.py` scopes every read/write to `{"user": current_user["_id"]}` — this is the correct ownership pattern, and (along with `proposals.py` from Part 1) is now confirmed in two independent files, reinforcing that the gap in `rfp_respond.py` (Part 1, §4.1) is a one-off inconsistency, not a systemic design gap.

## 18. Updated priority list (supersedes §11 — do these in order)

| Priority | Item | Why it's first | Effort |
|---|---|---|---|
| **P0** | Fix the 29 unauthenticated `fetch()` calls across 8 frontend files (§13) — route them through `api.js` | The product does not currently function against its own backend for Companies, Company Detail, AI Research, Proposal Builder, Tenders, and Reports | 3–6 hrs + click-through testing |
| **P0** | Fix the 4 broken download/preview links in Reports.jsx / RFPAutoRespond.jsx (§14) | Same category — a shipped, advertised feature (download your generated proposal) doesn't work | 2–3 hrs |
| **P0** | Remove hardcoded `localhost:5050` from the 8 affected files (§15) | Blocks deploying the frontend anywhere but a specific dev machine; same fix as the two items above | included above |
| **P1** | Fix `_subject_safe()` NameError in `mailer.py` (§16.1) | Every meeting invite/cancellation email silently fails today | 15 min |
| **P1** | Rotate credentials from the uploaded `.env`; commit the `PPT-Agent-bidforge-integration` deletion | Carried over from Part 1 — still open | ~35 min |
| **P1** | Add ownership check to `rfp_respond.py` status/download; gate `/companies/settings/ai-mode` behind `require_admin` and move it off file-rewrite (§16.2) | Carried over + new — both are auth/authorization gaps | 2–4 hrs |
| **P2** | Validate `/companies/import` JSON path against a schema (§16.3); add a sync cooldown to `/tenders/sync` (§16.4) | Data integrity + shared-resource exhaustion | 2–3 hrs combined |
| **P2** | Sign/validate OAuth `state` in `integrations.py`; fix `JWT_EXPIRES_IN`/`OTP_LENGTH` dead config (carried over from Part 1) | Still open | 2 hrs |
| **P2** | Convert blocking-only `async def` DB routes to `def`, or adopt `motor` (carried over) | Still open, matters more once real traffic shows up | 2–4 hrs |
| **P3** | File upload size/page caps (§16.6); decide on `matchScore` (§16.7); `requester` default (§16.8); everything else marked Low above | Polish, not blockers | Ranges from 15 min to 1 day |
| **P3** | First backend + frontend test pass, CI workflow, dependency pinning (carried over from Part 1) | Still the biggest structural gap, but nothing above should ship without working tests around it first | Multi-day, ongoing |

