# .archive/linki-integration-2026 — Archive README

**Date Archived:** 2026-08-19  
**Archived by:** Codebase cleanup per `02-migration-plan.md`

## Why These Files Were Archived

As per the Integration Plan v2, the following modules are being extracted from PPT-Agent (OrbitAvanya) and migrated to the **linki** service, which will host the automation engines as a standalone backend service.

PPT-Agent will be rebuilt as an **API client** that delegates these features to linki.

## What's Here

### frontend/pages/
- LinkedInOutreach.jsx — Full LinkedIn campaign UI (2362 lines)
- EmailCampaign.jsx — Email campaign management UI (2160 lines)
- Newsletter.jsx — Newsletter creation & scheduling UI
- CRMPipeline.jsx — CRM pipeline Kanban board UI

### frontend/components/
- EmailBeautifyModal.jsx — AI email HTML beautification modal

### frontend/data/
- companies.jsx, misc.jsx, tenders.jsx — Static mock data files (phased out for live API)

### backend/routes/
- campaigns.py, leads.py, tracking.py, newsletters.py
- linkedin_campaigns.py, linkedin_inbox.py, linkedin_accounts.py

### backend/core/
- linkedin_worker.py, email_worker.py, action_scheduler.py

### backend/pipeline/
- linkedin/ (entire directory), outreach_prompts.py

### backend/scripts/
- All ad-hoc debug & test scripts (20+ test_*.py files)

## Rollback
To restore any file, copy it from this archive back to its original path.

## Important: Database Tables NOT Dropped
MySQL tables (Campaign, Lead, Newsletter, LinkedInAccount, etc.) were NOT dropped.
Data is preserved for rollback and migration.
