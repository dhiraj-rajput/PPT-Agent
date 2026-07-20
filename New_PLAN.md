# OrbitAvanya (PPT-Agent) — Implementation Plan

**Status:** Planning document only. No files have been changed. This is the result of a full,
file-by-file review of the uploaded project (every `.py` file was opened or grepped, every
`.py` file was syntax-compiled, the import graph was traced for orphaned modules, and three
suspected bugs were actually executed to confirm them rather than guessed at).

This document is organized as a set of **phases** you can execute independently, in the order
listed. Each phase has: what's wrong today (with exact file/line evidence), what to do about
it, the steps in order, and how to know it worked before moving to the next phase.

---

## Table of Contents

1. [Audit Summary — Bugs, Dead Code, Integration Gaps](#1-audit-summary)
2. [Phase 1 — Repository Restructuring](#phase-1--repository-restructuring)
3. [Phase 2 — Document Generation Overhaul](#phase-2--document-generation-overhaul)
4. [Phase 3 — Newsletter Feature](#phase-3--newsletter-feature)
5. [Phase 4 — Cleanup & Hardening](#phase-4--cleanup--hardening)
6. [Suggested Execution Order & Milestones](#6-suggested-execution-order--milestones)
7. [Open Questions (need your input before coding starts)](#7-open-questions)

---

## 1. Audit Summary

### 1.1 Architecture as it actually exists today

The project is **not** a PowerPoint generator despite the folder name — it's a proposal/RFP
automation SaaS ("OrbitAvanya", formerly "PPT-Agent"). Three layers:

- **Frontend**: React 18 + Vite + Tailwind, currently at `Frontend/orbitavanya/` (double-nested).
- **Backend API**: FastAPI, entry point `server.py`, routes in `app/routes/*.py` (24 route
  modules — auth, users, tasks, meetings, companies, tenders, proposals, rfp_respond,
  campaigns, leads, tracking, analytics, naics, etc).
- **Research pipeline**: LangGraph-orchestrated agents in `pipeline/` (LinkedIn scraper,
  website crawler, Google/Tavily search, AI compactor) feeding a MongoDB-backed company
  intelligence store.
- **Document generation**: split across **three separate, duplicated engines** (see §1.3).

The README already describes a target layout (`frontend/`, `api/`) that the actual repo
doesn't match yet — so the restructuring below isn't a new idea, it's finishing what the
README already assumes.

### 1.2 Confirmed bugs (reproduced, not guessed)

| # | File | Issue | Evidence |
|---|------|-------|----------|
| 1 | `pipeline/linkedin/demo_compare.py`, `inspect_mongo.py`, `run_test.py` | `sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))` resolves to `pipeline/`, not the project root (needs a 3rd `dirname()`). | I ran `python3 pipeline/linkedin/demo_compare.py` exactly as its own docstring instructs — it crashes with `ModuleNotFoundError: No module named 'utils'`. |
| 2 | `restore.py` | Hardcodes `mongodb://localhost:27017/` and database name `"company_scraper"`, ignoring `config/settings.py` entirely. The live app's default DB name is `ppt_agent_db` (`MONGO_DB_NAME` in `config/settings.py`). Running this script restores data into a database the running app never reads from. Also expects a `company_scraper_db.zip` that doesn't exist anywhere in the repo. | Direct read of `restore.py` vs `config/settings.py`. |
| 3 | `.DS_Store` (root) and `Frontend/.DS_Store` are **tracked in git** | macOS junk files committed to the repo; `.gitignore` has no `.DS_Store` rule at all. | `git ls-files \| grep DS_Store` |
| 4 | `output/pdf/GSA-26-AI-0042_subcontract_proposal.docx` | A `.docx` sitting inside a folder named `pdf/` — a silent sign that LibreOffice PDF conversion failed for that run and the code fell back to returning the `.docx` without renaming/relocating it or surfacing the failure to the user. | Directory listing; confirmed by reading `_try_convert_to_pdf()` in `document_generator.py`, which swallows the conversion exception and just returns the `.docx` path. |
| 5 | Every file in the repo shows as 100%-changed in `git diff` against `HEAD` | This is CRLF/LF churn, not real edits — the git history has LF blobs, the working tree is checked out as CRLF (Windows `core.autocrlf`), and there's no `.gitattributes` to pin it down. Not a functional bug, but it will make every future PR look enormous and hide real changes in review. | `git diff --stat app/routes/campaigns.py` → 429 insertions / 429 deletions on a 429-line file. |

### 1.3 The root cause of your document-generation complaint (confirmed)

You have **three parallel document-generation engines** that all share the same structural flaw:

- `scripts/proposal_generator.py` — the "default OrbitAvanya template" engine (cfg-driven,
  builds cover page + TOC + sections from scratch).
- `documents/rfp_response/pdf_generator.py` + `rfp_response_pdf.py` — used by the RFP
  Auto-Respond feature.
- `documents/bidforge/document_generator.py` + `template_filler.py` — used by the
  cold-upload "BidForge" flow, and the one that does **literal fill-in-the-blank**: it
  walks the uploaded template's headings and inserts AI text directly after each one,
  using the template's own body style but with **no concept of the template's designed
  page geometry**.

Grepping for `page_break_before` across the repo shows the actual bug:

```
scripts/proposal_generator.py:395:  if section.get("page_break_before", True): doc.add_page_break()
documents/rfp_response/pdf_generator.py     — 5 sections hardcode True
documents/rfp_response/rfp_response_pdf.py  — 8 sections hardcode True
documents/bidforge/document_generator.py    — 7 sections hardcode True
```

**Every section in every one of the three engines forces a new page**, regardless of how
much room is left on the current page and regardless of how short the next section is. A
short "Next Steps" section (two sentences + a signature block) still starts on its own
fresh page — which is exactly your "blank / near-blank pages" symptom. Separately, because
no part of the pipeline tells the AI how much text a section is supposed to fill, generated
text length is uncorrelated with the space available, producing the "two or three words
spill onto the next page" widow/orphan symptom.

There's also a **dead class that is the missing piece of the real fix**:
`documents/rfp_response/docx_parser.py` defines `DOCXTemplateParser`, which already extracts
color palette, fonts, section structure, and page geometry from an uploaded `.docx`. It is
**never imported by any other file in the codebase** — it was clearly built for exactly this
purpose and never wired in. Phase 2 below is built around finally using it.

### 1.4 Dead code / orphaned files

Found by compiling every `.py` file (all pass — no syntax errors) and cross-referencing every
module against every `import` statement in the repo:

| File | Status | Recommendation |
|---|---|---|
| `documents/rfp_response/docx_parser.py` (`DOCXTemplateParser`) | Orphaned — 0 importers | **Wire in** (Phase 2), don't delete |
| `pipeline/linkedin/demo_compare.py` | Not imported anywhere; broken (bug #1) | Move to `scripts/dev/`, fix path bug |
| `pipeline/linkedin/inspect_mongo.py` | Same | Same |
| `pipeline/linkedin/run_test.py` | Same | Same |
| `restore.py` | Not imported; references nonexistent backup zip; wrong DB name | Fix or move to `scripts/dev/` with a big warning comment |
| `scripts/search_rfps.py`, `parse_sam.py`, `generate_pitch.py` | Not called by the web app (not a bug — these are intentionally operator-run CLI tools per the README) | Keep, just document clearly as "manual ops tools," not app-integrated |

For contrast, `scripts/bidforge_cli.py` and `scripts/respond_to_rfp.py` **are** used — they're
invoked via `subprocess` from `app/routes/rfp_respond.py` and `app/routes/proposals.py`. That's
a legitimate (if slightly unusual) integration pattern — flagging it in §1.5, not as dead code.

### 1.5 Integration gaps / design smells

1. **Subprocess-based pipeline invocation.** `app/routes/rfp_respond.py` and
   `app/routes/proposals.py` shell out to `python scripts/bidforge_cli.py` /
   `scripts/respond_to_rfp.py` as subprocesses and scrape `"Step N: ..."` lines from stdout
   for progress. This works but is fragile (no structured error propagation, no timeout
   handling visible at the route level, progress parsing breaks if log wording changes) and
   means the entire pipeline runs single-threaded per request outside FastAPI's async model.
   Not something to rip out during this project, but worth a ticket later to move to a real
   task queue (e.g. Celery/RQ/arq) if usage grows.
2. **Three document-generation engines, one bug, fixed in none of them.** Consolidating is
   out of scope for this pass (too risky to merge three engines at once), but Phase 2 fixes
   the shared root cause in a way that's copy-paste consistent across all three.
3. **`requirements.txt` lists unused dependencies**: `python-pptx` (leftover from the
   project's original literal-PowerPoint concept — zero imports anywhere), `langchain` and
   `langchain-openai` (only `langgraph` is actually imported; `langchain-core` is a
   transitive dependency of `langgraph` and doesn't need to be a direct one). Verified via
   `grep -rl "from pptx\|import pptx"` and `grep -rl "from langchain"` — zero hits outside
   `requirements.txt` itself.
4. **No `.gitattributes`** — see CRLF issue above.
5. **Campaign/lead/tracking system is solid and already does 80% of what "newsletter" needs**
   (see Phase 3) — the gap is just that leads can only be added via manual entry or CSV
   import today (`app/routes/leads.py`), not pulled from the `companies` collection.

### 1.6 What's already good (so Phase work below doesn't reinvent it)

- `app/core/auth.py` fails fast at import time if `JWT_SECRET` is missing/weak — correct.
- `app/routes/tracking.py` unsubscribe flow already uses a signed HMAC token
  (`app/core/tracking_helpers.py: unsubscribe_url` / `verify_unsubscribe_token`), writes to
  a global `suppressions` collection (unique index on email), and is checked at lead-import
  time (`leads.py`) — this is a correct, reusable foundation for the newsletter feature.
- `pipeline/ai/mode.py`'s `run_with_fallback()` (AI-first, rule-based fallback, 429-aware) is
  a clean pattern already used consistently across agents — the new "options" stage in
  Phase 2 should follow it rather than inventing a new pattern.
- `config/settings.py` is a well-structured single source of truth (pydantic-settings,
  typed, `.env`-driven) — no secrets are hardcoded anywhere in the codebase.
- `private/`, `output/`, `downloads/` are correctly `.gitignore`d already — no sensitive data
  is actually committed to git despite living in the working tree.

---

## Phase 1 — Repository Restructuring

**Goal:** `backend/` holds all Python source + data dirs; `frontend/` holds the flattened
React app (no more `Frontend/orbitavanya/` double-nesting); dead/junk files are gone or
gitignored.

### 1.1 Target layout

```
/ (repo root)
├── backend/
│   ├── app/                # FastAPI routes, core (auth, mailer, tracking), sam_gov
│   ├── config/              # settings.py
│   ├── documents/           # bidforge/, rfp_response/ generators
│   ├── pipeline/            # ai/, linkedin/, website/, google_search/, orchestrator/, models/
│   ├── scripts/             # CLI tools (+ new scripts/dev/ for debug-only scripts)
│   ├── tests/
│   ├── utils/
│   ├── assets/               # logo.png, cover_graphic.png
│   ├── docs/
│   ├── downloads/            # gitignored — runtime data
│   ├── output/                # gitignored — generated proposals
│   ├── private/               # gitignored — uploads, CSVs
│   ├── main.py
│   ├── server.py
│   ├── restore.py
│   └── requirements.txt
├── frontend/
│   ├── src/
│   ├── public/
│   ├── package.json
│   └── ... (everything currently under Frontend/orbitavanya/, flattened)
├── README.md
├── .gitignore
└── .gitattributes            # new — fixes CRLF churn
```

### 1.2 Why this is safe (no import breakage)

Every file inside `backend/` computes its own paths relative to itself
(`Path(__file__).resolve().parent...`) or relative to the process's working directory. As
long as the **whole backend subtree moves together as one unit**, all internal imports
(`from utils.db_client import ...`, `from app.routes.companies import ...`) keep working
unchanged — only the directory you `cd` into before running `python server.py` changes
(`cd backend && python server.py` instead of running from repo root). No Python import
statements need to change.

### 1.3 Steps, in order

1. **Snapshot first.** Commit or branch the current (dirty) working tree before touching
   anything, specifically because of the CRLF churn noted in §1.2 of the audit — you want a
   clean rollback point.
2. `git mv app config documents pipeline scripts tests utils assets docs downloads output private main.py server.py restore.py requirements.txt backend/`
   (using `git mv` rather than plain `mv` so history/blame survives the move).
3. `git mv Frontend/orbitavanya/* frontend/` then `git rm -r Frontend/` (or delete the now-empty
   folder) — this removes the double-nesting.
4. Delete tracked junk: `git rm --cached .DS_Store Frontend/.DS_Store` (paths may differ post-move;
   run `git ls-files | grep DS_Store` again to confirm none remain tracked).
5. Move the three broken dev-only LinkedIn scripts:
   `git mv backend/pipeline/linkedin/demo_compare.py backend/scripts/dev/linkedin_demo_compare.py`
   (same for `inspect_mongo.py`, `run_test.py`) — and while moving them, fix the `sys.path`
   bug from §1.2 (add the missing third `dirname()` call, or better, switch to a single line:
   `sys.path.insert(0, str(Path(__file__).resolve().parents[2]))` since they'll now be one
   directory deeper).
6. Update `.gitignore` (root) — change `/output/`, `/private/`, `/downloads/` to
   `backend/output/`, `backend/private/`, `backend/downloads/`; add `.DS_Store`,
   `**/.DS_Store`, and `frontend/bun.lock` (keep one lockfile — see §4.3).
7. Add `.gitattributes` at repo root:
   ```
   * text=auto eol=lf
   *.png binary
   *.pdf binary
   *.docx binary
   ```
8. Update `README.md`: change install/run instructions to `cd backend` before
   `pip install -r requirements.txt` / `python server.py`, and `cd frontend` before
   `npm install` / `npm run dev` (the README already assumed this layout — just needs the
   paths to now be true).
9. Update any absolute/deploy-time paths outside the repo (systemd unit files, Docker
   `WORKDIR`, CI YAML, PM2 configs — none exist in this repo currently, but check your
   deployment environment separately, since this restructuring changes the "run from"
   directory).

### 1.4 Acceptance criteria before moving to Phase 2

- [ ] `cd backend && python -m py_compile $(find . -name "*.py")` — no errors.
- [ ] `cd backend && python server.py` boots without `ModuleNotFoundError`.
- [ ] `cd frontend && npm install && npm run dev` boots and can reach the backend at the
      configured `VITE_API_URL`.
- [ ] `git ls-files | grep -i ds_store` returns nothing.
- [ ] `git status` no longer shows CRLF-only diffs on files you haven't touched (may require
      a one-time `git add --renormalize .` after adding `.gitattributes`).

---

## Phase 2 — Document Generation Overhaul

This phase has three independent pieces. They can be built and shipped in this order — each
is useful on its own, and each de-risks the next.

### 2.1 Piece A — Kill the forced-page-break bug (highest impact, lowest risk)

**Problem (recap):** every section across all three generation engines hardcodes
`page_break_before: True`, producing sparse/blank pages.

**Fix:**
1. In `scripts/proposal_generator.py`, change `add_section()`'s default from
   `section.get("page_break_before", True)` to `False`, and instead of a blanket page break,
   use Word's real "keep together" formatting:
   - Set `paragraph_format.keep_with_next = True` on section heading paragraphs, so a
     heading never gets orphaned alone at the bottom of a page (Word/LibreOffice push the
     whole heading+first-line block to the next page automatically instead of a manual
     break).
   - Set `paragraph_format.widow_control = True` document-wide (via `doc.styles["Normal"]`)
     to stop 1–2 line orphans/widows — this directly targets the "two or three words on the
     next page" symptom, and it's a two-line change.
   - Reserve **explicit** `page_break_before: True` for only the first section after the TOC
     (so the body doesn't start mid-page) — every caller in `document_generator.py`,
     `pdf_generator.py`, and `rfp_response_pdf.py` needs its per-section flags reviewed and
     changed from "always True" to "True only on the first section, False elsewhere."
2. Apply the identical change to the other two engines
   (`documents/rfp_response/pdf_generator.py`, `documents/rfp_response/rfp_response_pdf.py`)
   — same default flip, same keep-with-next/widow-control settings. This is mechanical once
   the pattern is proven in `proposal_generator.py`.

**Test:** generate one sample proposal through each of the three engines before/after, open
each PDF, and manually check that (a) no page has more than ~30% whitespace unless it's the
intentional last page of a section, and (b) no line at the top of a page has fewer than ~4
words orphaned from the previous page.

### 2.2 Piece B — Content-length budgeting (fixes the *cause*, not just the symptom)

**Problem:** the AI prompt in `documents/bidforge/document_generator.py`
(`_generate_sections_ai`) explicitly tells the model *"the document has no page limit... do
not artificially shorten sections"* — there is no signal at all about how much text a section
should produce relative to available page space. That's why some sections run short (leaving
whitespace) and others run long (spilling into orphan lines).

**Fix:**
1. Add a small shared helper, e.g. `documents/generation_layout.py`, with:
   - A word-per-page constant derived from the actual page geometry used
     (`Inches(8.5) x 11`, 0.75" margins, 11pt body) — roughly 480–520 words/page for prose,
     adjustable per template once Piece C (below) can measure a real template.
   - A function `section_word_budget(section_key: str, target_total_pages: int) -> tuple[int,int]`
     that returns a `(min_words, max_words)` band per section type, based on a configurable
     weight table (e.g. Executive Summary ≈ 1 page, Scope of Work ≈ 1.5–2.5 pages, Pricing is
     mostly table/not prose-bound, Terms ≈ 0.5 page, etc).
2. Pass those bands into the AI prompt explicitly per section
   (`"executive_summary: write between 380 and 520 words"` etc.) instead of "no limit."
3. Add a **lightweight post-check**, no external tools required: after the AI JSON comes
   back, count words per section (`len(text.split())`) and compare against the budget. If a
   section is <60% or >150% of its target, make **one** bounded retry call asking the model
   specifically to expand or condense just that section (not the whole document) — this keeps
   the loop cheap and avoids needing LibreOffice/page-rendering just to validate length.

**Test:** generate 5 sample proposals, log word counts per section pre/post-retry, confirm the
retry rate is low (<20% of sections) and that retried sections land inside their band on the
second try.

### 2.3 Piece C — Template-derived full generation (the deeper fix you actually asked for)

**Problem (recap):** `template_filler.py` does literal fill-in-the-blank: find a heading in
the uploaded template that fuzzy-matches a known section name, insert AI text right after it
using the template's body style. It never looks at the template's actual design (colors,
fonts, logo placement, typical section length) — it only borrows the style *name*.

**Fix — wire in the orphaned `DOCXTemplateParser`:**
1. In `documents/bidforge/document_generator.py`, when a `template_path` is provided, call
   `DOCXTemplateParser(template_path).parse()` (from `documents/rfp_response/docx_parser.py`)
   **first**, before deciding how to fill it. It already extracts: color palette, fonts,
   section/TOC structure, header/footer layout, and page dimensions/margins.
2. Feed those extracted values into a `brand` config dict shaped exactly like the one
   `scripts/proposal_generator.py:generate()` already expects (`company_name, logo_path,
   body_font, heading_font, accent_color, muted_color, ...`) — most of these map directly
   from what `DOCXTemplateParser` already returns.
3. Run the **full** `proposal_generator.generate()` pipeline (cover page, TOC, sections,
   headers/footers) using the *extracted* brand config, instead of the current "insert
   paragraphs after matching headings" approach. This produces a from-scratch document that
   actually looks like the uploaded template, rather than one that's had text spliced into it.
4. Keep the current `template_filler.py` logic as an **explicit fallback** — if
   `DOCXTemplateParser` can't confidently extract enough structure (e.g. a template with no
   heading styles at all, or a scanned/image-based template), fall back to today's
   insert-after-heading behavior rather than failing outright.
5. Reuse the per-page word budget from Piece B, but now calibrated against the *actual*
   original template page count (which `DOCXTemplateParser` can report) instead of a generic
   default.

**Why this order (C after A and B):** Piece C is the highest-value fix but also the riskiest
(it changes what "template mode" produces, not just how it's paginated) — shipping A and B
first gives you working, safer improvements while C is being built and tested against a range
of real uploaded templates.

### 2.4 New: pre-generation "options" stage

**What you asked for:** before the document is fully generated, the model should propose a
small number of directions (e.g. 3 options — tone, structural emphasis, or pricing framing) and
let you pick one before the final document is written.

**Design (follows the existing `run_with_fallback` AI/rule-based pattern in `pipeline/ai/mode.py`):**
1. New function, e.g. `documents/bidforge/generation_options.py::propose_document_options()`:
   - Input: the same `parsed_rfp / inventory / competitor_intel / strategy` data already
     available at the point `generate_final_document()` is called.
   - Output: a JSON array of exactly 3 options, each with `{id, label, description,
     tone, emphasis}` — e.g. "Cost-Led" (leads with pricing/value), "Technical-Led"
     (leads with capability/scope depth), "Relationship-Led" (leads with prior work,
     differentiation, and a warmer executive summary). Rule-based fallback: 3 fixed,
     hardcoded option templates (no AI call) so the feature still works if AI is unavailable.
2. New API endpoints in `app/routes/rfp_respond.py` (and the equivalent in the BidForge route
   if separate):
   - `POST /api/rfp-respond/{id}/options` → runs `propose_document_options()`, stores the 3
     options against the in-progress job, returns them to the frontend.
   - `POST /api/rfp-respond/{id}/generate` → now requires `{"optionId": "..."}` in the body;
     the selected option's `tone`/`emphasis` fields get folded into the existing
     `_generate_sections_ai()` prompt as additional instructions.
3. Frontend (`RFPAutoRespond.jsx`): insert a new step between "upload/parse" and
   "generating final document" — a 3-card chooser (label + description per option), disable
   the "Generate" button until one is selected, then call `/generate` with the chosen
   `optionId`. This mirrors the existing multi-step wizard pattern already used in that page.
4. Apply the same pattern to `documents/rfp_response` (the other generation pipeline) once the
   BidForge version is validated — the endpoint and prompt shapes are the same, just pointed
   at `rfp_response_generator.py`'s existing prompt-building functions instead.

**Test:** run the options endpoint against 5 different real RFPs, confirm the 3 returned
options are meaningfully different from each other (not just reworded synonyms), and confirm
the selected option visibly changes tone/emphasis in the final generated document (spot-check
by reading, not automatable).

---

## Phase 3 — Newsletter Feature

### 3.1 Why this is mostly *reuse*, not new infrastructure

You already have, working today, in `app/core/tracking_helpers.py` + `app/core/mailer.py` +
`app/routes/tracking.py`:
- Secure HMAC-signed unsubscribe tokens (`unsubscribe_url()` / `verify_unsubscribe_token()`)
- Open-pixel and click-redirect tracking
- A global `suppressions` collection (unique index on email) checked at send/import time
- `send_company_email_with_attachments()` — a working async email sender

The newsletter feature is new **schema + endpoints + a frontend page**, wired to that existing
infrastructure — not a new mail pipeline.

### 3.2 Why a new collection set, not overloading `campaigns`/`leads`

`campaigns` and `leads` (in `app/routes/campaigns.py` / `leads.py`) model a **one-shot drip
outreach** flow: a lead moves once through `pending → sent → opened → clicked/replied`, spaced
out by a `dailyLimit`, and the campaign is "done" once every lead has been reached. A
newsletter is structurally different: a **persistent subscriber list** that receives **repeated,
separate editions** over time, where each edition needs its own open/click stats without
resetting the subscriber's overall status. Forcing that shape onto `campaigns`/`leads` would
require rewriting their lifecycle assumptions (pause/resume/launch, `dailyLimit` spacing) and
risks breaking the existing outreach-campaign feature. A parallel, smaller schema is safer and
clearer to reason about — while still sharing the same low-level send/track/unsubscribe helpers.

### 3.3 Data model

```
newsletters               # one per newsletter "publication"
  _id, name, description, senderName, senderEmail, createdBy, createdAt, updatedAt
  stats: { totalSubscribers, totalSent, totalOpened, totalClicked, totalUnsubscribed }

newsletter_subscribers    # persistent list, decoupled from any single edition
  _id, newsletterId, companyId (ref -> companies._id, nullable), companyName,
  email, contactName, source ("company_db" | "manual" | "csv"),
  status ("subscribed" | "unsubscribed"), subscribedAt, unsubscribedAt, createdAt
  # unique index: (newsletterId, email)

newsletter_editions        # one per "issue" sent
  _id, newsletterId, subject, body, status ("draft" | "sending" | "sent"),
  scheduledFor (nullable), sentAt, stats: {sent, opened, clicked, unsubscribed},
  createdBy, createdAt

newsletter_sends           # per-subscriber, per-edition send record (keeps history across editions)
  _id, editionId, newsletterId, subscriberId, email, trackingId,
  status, sentAt, openedAt, clickedAt, error
```

### 3.4 Backend endpoints (new file: `app/routes/newsletters.py`)

| Method & Path | Purpose |
|---|---|
| `POST /api/newsletters` | Create a newsletter |
| `GET /api/newsletters` | List newsletters (current user's) |
| `GET /api/newsletters/{id}` | Detail + stats |
| `PATCH /api/newsletters/{id}` | Update name/sender info |
| `DELETE /api/newsletters/{id}` | Delete (and cascade subscribers/editions) |
| `GET /api/newsletters/{id}/subscribers` | Paginated list, filter by status |
| `POST /api/newsletters/{id}/subscribers/from-companies` | Body: `{companyIds: [...]}` **or** `{filter: {naics, size, query}}` — pulls from the existing `companies` collection (which already has an `email` field from the SAM.gov import), dedupes against existing subscribers, checks the global `suppressions` collection, inserts as `status: subscribed` |
| `POST /api/newsletters/{id}/subscribers` | Add one subscriber manually |
| `POST /api/newsletters/{id}/subscribers/import/csv` | Bulk CSV import (mirrors the existing logic in `leads.py::import_leads_csv`) |
| `DELETE /api/newsletters/{id}/subscribers/{subId}` | Remove a subscriber |
| `POST /api/newsletters/{id}/editions` | Create an edition; body includes `sendNow: bool` or `scheduledFor` |
| `GET /api/newsletters/{id}/editions` | List past editions with stats |
| `GET /api/newsletters/{id}/editions/{editionId}` | Edition detail |
| `GET /api/newsletters/tracking/open/{trackingId}.png` | Open-pixel (parallel to existing tracking route, but updates `newsletter_sends`/`newsletter_editions` instead of `leads`/`campaigns`) |
| `GET /api/newsletters/tracking/click/{trackingId}` | Click redirect (same pattern) |
| `GET /api/newsletters/unsubscribe/{newsletterId}/{subscriberId}?t=...` | Public unsubscribe — reuses the existing HMAC token verify function generalized to accept `(subscriberId, newsletterId)`; marks the subscriber unsubscribed **and** writes to the shared global `suppressions` collection so a person who unsubscribes stops receiving *anything*, not just this newsletter |

Sending an edition: iterate `newsletter_subscribers` where `status = "subscribed"` and email
is not in `suppressions`, call the existing `send_company_email_with_attachments()` per
recipient with the tracking pixel + rewritten click links injected into the body (reuse
`rewrite_links_for_tracking()`), write one `newsletter_sends` row per recipient. For v1, a
simple rate-limited loop (reusing the spacing pattern from
`campaigns.py::_queue_pending_leads`) is enough — a full background worker like
`app/core/email_worker.py` can be added later if daily-newsletter volume grows.

### 3.5 Frontend

New page `frontend/src/pages/Newsletter.jsx`, new route `/newsletter` in `App.jsx`, new
sidebar entry in `Sidebar.jsx`. Structure (reusing existing UI patterns already in
`EmailCampaign.jsx` and `Companies.jsx`):

1. **Newsletter list/create** — same list+create-modal pattern as `EmailCampaign.jsx`.
2. **Subscriber management tab** — reuse the existing companies table/filter UI from
   `Companies.jsx` (search, NAICS filter, size filter — it already calls `GET /api/companies`)
   with checkboxes added, plus a manual-add form and CSV import, and an "Add selected to
   newsletter" action calling the new `from-companies` endpoint.
3. **Compose & send tab** — subject/body editor (can reuse whatever rich-text component
   `EmailCampaign.jsx` already uses for its body field), a live subscriber-count preview, and
   a "Send now" / "Schedule" action.
4. **Edition history tab** — table of past editions with sent/opened/clicked/unsubscribed
   stats, mirroring the stats cards already built for `EmailCampaign.jsx`.

No separate frontend page is needed for the unsubscribe landing — like the existing campaign
unsubscribe flow, it's a small server-rendered HTML response from the backend route itself.

### 3.6 Acceptance criteria

- [ ] Selecting 20 companies from the Companies view and adding them to a newsletter creates
      20 `newsletter_subscribers` rows, skipping any that are already in the global
      `suppressions` collection.
- [ ] Sending an edition delivers to all `subscribed` subscribers, records a `newsletter_sends`
      row per recipient, and increments `newsletter_editions.stats.sent`.
- [ ] Opening the email increments `stats.opened` exactly once per subscriber per edition
      (repeat opens logged but not double-counted, matching the existing campaign tracking
      behavior).
- [ ] Clicking the unsubscribe link marks the subscriber `unsubscribed`, adds their email to
      the global `suppressions` collection, and a second newsletter (different `newsletterId`)
      sent afterward also excludes them.
- [ ] Sending a second edition to the same newsletter does **not** require re-adding
      subscribers and correctly excludes anyone who unsubscribed after edition 1.

---

## Phase 4 — Cleanup & Hardening

Small, independent items that can be done anytime after Phase 1:

1. **Trim `requirements.txt`**: remove `python-pptx`, `langchain`, `langchain-openai`
   (re-verify with `pip check` after removal that `langgraph` still resolves its own
   `langchain-core` dependency correctly).
2. **Fix or retire `restore.py`**: either point it at `config/settings.py`
   (`settings.MONGO_URI` / `settings.MONGO_DB_NAME`) instead of hardcoded values, or move it
   to `backend/scripts/dev/` with a clear header comment that it's an old/manual tool and
   confirm whether `company_scraper_db.zip` is still a real artifact anyone produces.
3. **Line-ending normalization**: after adding `.gitattributes` (Phase 1), run
   `git add --renormalize .` once and commit, so future diffs are real diffs.
4. **Pick one JS package manager**: `package-lock.json` (npm) is the one that's actually
   git-tracked; `bun.lock` was a stray local file from someone running `bun install` once.
   Either commit to npm (delete `bun.lock`, update README to drop the "or bun" mention) or
   switch fully to bun (delete `package-lock.json`, update CI/README) — don't keep both.
5. **Structured logging pass**: several route/pipeline files use bare `print()` instead of
   the project's own `setup_logger()` (already used consistently elsewhere, e.g.
   `utils/helpers.py`) — `app/routes/{naics,auth,integrations,proposals,tenders,reports,
   companies,tracking,rfp_respond}.py` and a handful of `pipeline/`/`documents/` files. Low
   priority, but worth a pass so production logs are consistent and filterable.

---

## 6. Suggested Execution Order & Milestones

```
Week 1:  Phase 1 (restructuring)              — low risk, unblocks everything else
Week 1:  Phase 2.1 (page-break fix)            — highest complaint-impact, ~1 day of work
Week 2:  Phase 2.2 (content-length budgeting)  — builds on 2.1
Week 2:  Phase 4 items 1–4                     — can run in parallel with anything
Week 3:  Phase 3 (newsletter backend)          — schema + endpoints
Week 3:  Phase 3 (newsletter frontend)
Week 4:  Phase 2.3 (template-derived generation via DOCXTemplateParser) — highest value,
         save for after the rest is stable since it changes template-mode output
Week 4:  Phase 2.4 (pre-generation options stage)
```

Each phase above has its own acceptance criteria section — treat those as the definition of
"done" before starting the next phase, not as a final QA pass at the end.

---

## 7. Open Questions

Answering these before implementation starts will avoid rework:

1. **Newsletter sending volume/cadence** — is "daily" a literal requirement (needs a
   scheduler/cron or background worker from day one) or does "select companies → send when I
   click send" cover the real need, with recurring scheduling as a fast-follow?
2. **Newsletter content source** — will you always write the edition body by hand, or should
   the AI client also draft newsletter content (reusing the `pipeline/ai/client.py`
   abstraction), similar to how proposal sections are AI-drafted?
3. **Template-derived generation (Phase 2.3) fallback threshold** — how should the system
   decide a template is "not confidently parseable" and should fall back to the current
   fill-in-heading behavior? (e.g. no heading styles found at all, fewer than N headings,
   parsing exception) — worth agreeing on the specific rule before building it.
4. **Options stage (Phase 2.4) scope** — start with BidForge only, or build it for both
   BidForge and the RFP Auto-Respond pipeline in the same pass?
5. **Deployment environment** — Phase 1 changes the working directory the app runs from
   (`cd backend` first). If there's a server/CI/Docker setup not included in this zip, it
   needs the equivalent path update — worth confirming what that environment looks like.
