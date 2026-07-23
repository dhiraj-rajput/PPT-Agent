"""
server.py
----------
OrbitAvanya — FastAPI backend entry point.

Runs all API routes on a single server (port 5050 by default).

Routes:
  /api/auth/*          — register, login, OTP, JWT, me
  /api/users/*         — user management + invite
  /api/tasks/*         — tasks CRUD + assignment
  /api/meetings/*      — meetings + Jitsi/Zoom/Google Meet
  /api/notifications/* — in-app alerts
  /api/integrations/*  — Google OAuth for Meet
  /api/companies/*     — company intelligence
  /api/tenders/*       — SAM.gov tender opportunities
  /api/proposals/*     — AI proposal generation
  /api/reports/*       — analytics reports
  /api/rfp-respond/*   — RFP Auto-Respond (AI proposal from uploaded RFP)
"""

import os
import uvicorn
from dotenv import load_dotenv

load_dotenv()

# NOTE: OAUTHLIB_RELAX_TOKEN_SCOPE removed — it allows scope weakening in production.
# If you need it for specific Google OAuth flows during development only, set it in .env.

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from utils.db_client import (
    close_connection,
    init_motor_client,
    close_motor_client,
)

# ---- Core feature routes ----
from app.routes.companies import router as companies_router
from app.routes.reports import router as reports_router
from app.routes.proposals import router as proposals_router
from app.routes.tenders import router as tenders_router

# ---- Auth & user management ----
from app.routes.auth import router as auth_router
from app.routes.users import router as users_router
from app.routes.tasks import router as tasks_router
from app.routes.meetings import router as meetings_router
from app.routes.notifications import router as notifications_router
from app.routes.integrations import router as integrations_router

# ---- RFP Auto-Respond ----
from app.routes.rfp_respond import router as rfp_respond_router

# ---- Preview / Pre-generation wizard ----
from app.routes.preview import router as preview_router

# ---- Email Outreach & Campaign Module ----
from app.routes.campaigns import router as campaigns_router
from app.routes.leads import router as leads_router
from app.routes.tracking import router as tracking_router
from app.routes.analytics import router as analytics_router
from app.routes.website_events import router as website_events_router
from app.routes.naics import router as naics_router
from app.routes.newsletters import router as newsletters_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    import asyncio
    import logging
    _log = logging.getLogger("server")

    # ── Startup ────────────────────────────────────────────────────────────

    # 1. Initialise async Motor client (must happen before any async route uses DB)
    init_motor_client()
    _log.info("Motor async client initialised.")

    # 2. Load SAM entities CSV in a background thread (sync/heavy I/O)
    from app.routes.companies import import_sam_entities_csv
    await asyncio.to_thread(import_sam_entities_csv)

    # 3. Ensure all MongoDB indexes (sync, run in thread to avoid blocking event loop)
    def setup_indexes_sync():
        try:
            from utils.db_client import ensure_all_indexes, get_collection
            ensure_all_indexes()

            # Auth & user collections
            get_collection("users").create_index("email", unique=True)
            get_collection("otps").create_index([("userId", 1), ("purpose", 1)])
            get_collection("otps").create_index("expiresAt", expireAfterSeconds=0)
            get_collection("login_failures").create_index("createdAt", expireAfterSeconds=900)

            # Tasks & meetings
            get_collection("tasks").create_index("createdAt")
            get_collection("meetings").create_index([("date", 1), ("time", 1)])

            # Notifications
            get_collection("notifications").create_index([("user", 1), ("createdAt", -1)])
            get_collection("notifications").create_index([("user", 1), ("read", 1)])

            # Campaign & outreach
            get_collection("campaigns").create_index([("createdBy", 1), ("status", 1)])
            get_collection("leads").create_index([("campaignId", 1), ("email", 1)], unique=True)
            get_collection("suppressions").create_index("email", unique=True)
            get_collection("tracking_events").create_index(
                [("campaignId", 1), ("type", 1), ("timestamp", 1)]
            )
            get_collection("website_events").create_index(
                [("campaignId", 1), ("timestamp", 1)]
            )
        except Exception as e:
            logging.getLogger("server").warning(f"MongoDB index setup warning: {e}")

    await asyncio.to_thread(setup_indexes_sync)

    # 4. Start Background Email Worker Loop
    from app.core.email_worker import start_email_worker_loop
    worker_task = asyncio.create_task(start_email_worker_loop())
    _log.info("Email worker task started.")

    yield

    # ── Shutdown ───────────────────────────────────────────────────────────

    # 1. Cancel and await the email worker task
    worker_task.cancel()
    try:
        await worker_task
    except asyncio.CancelledError:
        _log.info("Email worker task cancelled cleanly.")
    except Exception as e:
        _log.warning(f"Email worker shutdown error: {e}")

    # 2. Close Motor async client
    close_motor_client()

    # 3. Close sync pymongo client (used by scripts/pipeline that may be active)
    close_connection()

    _log.info("Server shutdown complete.")


from config.settings import settings

app = FastAPI(
    title="OrbitAvanya Backend API",
    version="2.0",
    description="AI-powered tender intelligence, company research, and proposal generation platform.",
    lifespan=lifespan,
)

# Enable CORS for frontend connectivity
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---- Register all routers ----
app.include_router(auth_router, prefix="/api")
app.include_router(users_router, prefix="/api")
app.include_router(tasks_router, prefix="/api")
app.include_router(meetings_router, prefix="/api")
app.include_router(notifications_router, prefix="/api")
app.include_router(integrations_router, prefix="/api")
app.include_router(companies_router, prefix="/api")
app.include_router(reports_router, prefix="/api")
app.include_router(proposals_router, prefix="/api")
app.include_router(tenders_router, prefix="/api")
app.include_router(rfp_respond_router, prefix="/api")
app.include_router(preview_router, prefix="/api")

# Campaign & Outreach module routers
app.include_router(campaigns_router, prefix="/api")
app.include_router(leads_router, prefix="/api")
app.include_router(tracking_router, prefix="/api")
app.include_router(analytics_router, prefix="/api")
app.include_router(website_events_router, prefix="/api")
app.include_router(naics_router, prefix="/api")
app.include_router(newsletters_router, prefix="/api")

# Serve downloaded tender documents statically (needed for DocumentViewer)
from pathlib import Path
from fastapi.staticfiles import StaticFiles

_downloads_dir = Path("downloads")
_downloads_dir.mkdir(parents=True, exist_ok=True)
app.mount("/downloads", StaticFiles(directory=str(_downloads_dir)), name="downloads")


@app.get("/tracker.js")
def get_root_tracker_js():
    from app.routes.tracking import TRACKER_JS
    from fastapi.responses import Response
    return Response(content=TRACKER_JS, media_type="application/javascript")


@app.get("/api/health")
async def health():
    """Health check. Uses Motor async ping to avoid blocking the event loop."""
    try:
        from utils.db_client import get_async_db
        db = get_async_db()
        await db.command("ping")
        db_status = "healthy"
    except Exception as e:
        import logging
        logging.getLogger("server").error(f"Database health check failed: {e}")
        db_status = "unhealthy"

    return {
        "ok": db_status == "healthy",
        "service": "OrbitAvanya API v2.0",
        "dependencies": {
            "mongodb": db_status
        },
        "ai_status": {
            "strict_mode": settings.BIDFORGE_STRICT_AI,
            "ai_mode": settings.AI_MODE,
            "provider_order": settings.AI_PROVIDER_ORDER,
            "configured_providers": {
                "gemini": bool(settings.GEMINI_API_KEY),
                "openrouter": bool(settings.OPENROUTER_API_KEY),
                "ollama": bool(settings.OLLAMA_HOST or settings.OLLAMA_API_KEY),
            }
        }
    }


if __name__ == "__main__":
    reload_enabled = settings.ENV == "dev"
    # In GitHub Codespaces or Docker, bind to all interfaces
    host = (
        "0.0.0.0"
        if (settings.CODESPACES or os.getenv("CODESPACES") == "true")
        else "127.0.0.1"
    )
    uvicorn.run(
        "server:app",
        host=host,
        port=settings.PORT,
        reload=reload_enabled,
        timeout_keep_alive=600,
    )
