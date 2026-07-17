"""
server.py
----------
OrbitAvanya — FastAPI backend entry point.

Runs all API routes on a single server (port 8000), replacing the
separate Node.js auth server that previously ran on port 5000.

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

import uvicorn
from dotenv import load_dotenv
load_dotenv()

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from utils.db_client import close_connection

# ---- Core feature routes ----
from app.routes.companies import router as companies_router
from app.routes.reports import router as reports_router
from app.routes.proposals import router as proposals_router
from app.routes.tenders import router as tenders_router

# ---- Auth & user management (ported from Node.js) ----
from app.routes.auth import router as auth_router
from app.routes.users import router as users_router
from app.routes.tasks import router as tasks_router
from app.routes.meetings import router as meetings_router
from app.routes.notifications import router as notifications_router
from app.routes.integrations import router as integrations_router

# ---- RFP Auto-Respond (formerly BidForge) ----
from app.routes.rfp_respond import router as rfp_respond_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: load/verify SAM entities database + ensure MongoDB indexes
    from app.routes.companies import import_sam_entities_csv
    import_sam_entities_csv()

    # Ensure indexes for all collections (core + new auth collections)
    try:
        from utils.db_client import ensure_all_indexes, get_collection
        ensure_all_indexes()

        # Additional indexes for auth/tasks/meetings/notifications collections
        get_collection("users").create_index("email", unique=True)
        get_collection("otps").create_index([("userId", 1), ("purpose", 1)])
        get_collection("otps").create_index("expiresAt", expireAfterSeconds=0)
        get_collection("tasks").create_index("createdAt")
        get_collection("meetings").create_index([("date", 1), ("time", 1)])
        get_collection("notifications").create_index([("user", 1), ("createdAt", -1)])
        get_collection("notifications").create_index([("user", 1), ("read", 1)])
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"MongoDB index setup warning: {e}")

    yield
    # Shutdown: close DB connection
    close_connection()


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


@app.get("/api/health")
async def health():
    try:
        from utils.db_client import get_database
        db = get_database()
        db.command("ping")
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
        }
    }


if __name__ == "__main__":
    from config.settings import settings
    reload_enabled = (settings.ENV == "dev")
    uvicorn.run("server:app", host="127.0.0.1", port=settings.PORT, reload=reload_enabled)
