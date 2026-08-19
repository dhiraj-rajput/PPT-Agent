"""
server.py
----------
OrbitAvanya — FastAPI backend entry point using MySQL as the primary database.
"""

from __future__ import annotations

import sys
import asyncio


# ── Windows: switch to ProactorEventLoop BEFORE uvicorn/asyncio start ────────
# On Windows, the default SelectorEventLoop cannot spawn subprocesses, which
# means Playwright's chromium.launch() raises NotImplementedError when it tries
# to start the browser process. ProactorEventLoop (IOCP-based) supports
# subprocesses on Windows and is required for Playwright automation to work.
# This must happen before ANY asyncio or uvicorn import runs the event loop.
if sys.platform == "win32":
    import asyncio
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())


def proactor_loop_factory(use_subprocess: bool = False):
    """
    Custom loop factory for uvicorn on Windows.
    uvicorn 0.36+ defaults to SelectorEventLoop on Windows whenever use_subprocess=True
    (e.g., during reload or background tasks), which breaks Playwright subprocess launching.
    This factory explicitly returns an instance of asyncio.ProactorEventLoop so Playwright works cleanly.
    """
    return asyncio.ProactorEventLoop()
# ─────────────────────────────────────────────────────────────────────────────

import os
import uvicorn
import logging
from dotenv import load_dotenv

load_dotenv()

from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from utils.db_client import (
    close_connection,
    init_motor_client,
    close_motor_client,
    _mysql_available,
)

# ---- Core feature routes ----
from app.routes.companies import router as companies_router
from app.routes.people import router as people_router
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
from app.routes.templates import router as templates_router

# ---- Preview / Pre-generation wizard ----
from app.routes.preview import router as preview_router

# ---- Analytics (retained — read-only, no outreach engine) ----
from app.routes.analytics import router as analytics_router
from app.routes.naics import router as naics_router
from app.routes.sic import router as sic_router

# ---- Admin: Server Logs ----
from app.routes.system_logs import router as system_logs_router

_log = logging.getLogger("server")


# ── Background tasks strong-reference store ─────────────────────────────────
# asyncio.create_task() only holds a *weak* reference internally. If the
# returned Task object isn't stored elsewhere the GC may collect the task
# mid-run without any exception. We keep strong references here until
# completion so that cannot happen.
_bg_tasks: set = set()

def _spawn_task(coro_or_future) -> "asyncio.Task":
    """Create an asyncio task and keep a strong reference to it."""
    task = asyncio.ensure_future(coro_or_future)
    _bg_tasks.add(task)
    task.add_done_callback(_bg_tasks.discard)
    return task
# ─────────────────────────────────────────────────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup ────────────────────────────────────────────────────────────

    # 0. Initialise MySQL schema
    if _mysql_available:
        try:
            from utils.db_client import init_mysql
            await init_mysql()
            _log.info("MySQL schema initialized successfully.")
        except Exception as e:
            _log.error(f"Failed to initialize MySQL schema: {e}", exc_info=True)

    # 1. Initialise async Motor client (for legacy / document-heavy collections)
    init_motor_client()
    _log.info("Motor async client initialised.")

    # 2. Seed initial datasets & setup MongoDB indexes in a non-blocking background task
    def setup_bg_data():
        try:
            from app.routes.companies import import_sam_entities_csv
            from app.routes.naics import ensure_naics_populated
            from app.routes.sic import ensure_sic_populated
            from utils.db_client import ensure_all_indexes

            ensure_naics_populated()
            ensure_sic_populated()
            import_sam_entities_csv()
            ensure_all_indexes()
            _log.info("Background DB setup completed.")
        except Exception as e:
            _log.warning(f"Background DB setup warning: {e}")

    try:
        _spawn_task(asyncio.to_thread(setup_bg_data))
    except Exception as e:
        _log.warning(f"Could not spawn background DB setup thread: {e}")

    # 3. Start Background TTL Cleanup Loop (runs every 60 minutes)
    async def run_ttl_cleanup_loop():
        while True:
            try:
                from utils.db_client import _mysql_available
                if _mysql_available:
                    def _do_cleanup():
                        from utils.db_client import get_sync_db_session
                        from models.sql_models import ActiveLease, TaskStatus, ErrorLog, OTP
                        from sqlalchemy import delete
                        from datetime import datetime, timedelta, timezone
                        import logging
                        log = logging.getLogger("ttl_cleanup")
                        now = datetime.now(timezone.utc)
                        with get_sync_db_session() as db:
                            # 1. Clean expired active leases
                            db.execute(delete(ActiveLease).where(ActiveLease.expires_at < now))
                            # 2. Clean expired task statuses (1 day old)
                            db.execute(delete(TaskStatus).where(TaskStatus.last_updated < now - timedelta(days=1)))
                            # 3. Clean old error logs (30 days old)
                            db.execute(delete(ErrorLog).where(ErrorLog.timestamp < now - timedelta(days=30)))
                            # 4. Clean expired OTPs
                            db.execute(delete(OTP).where(OTP.expires_at < now))
                            db.commit()
                        log.info("[TTL Cleanup] Expired leases, tasks, logs, and OTPs cleaned.")

                    await asyncio.to_thread(_do_cleanup)
            except Exception as e:
                _log.warning(f"[TTL Cleanup] Failed running cleanup: {e}")
            await asyncio.sleep(3600)

    cleanup_task = _spawn_task(run_ttl_cleanup_loop())
    _log.info("TTL cleanup background loop task started.")

    yield

    # ── Shutdown ───────────────────────────────────────────────────────────

    # 1. Cancel background loops
    cleanup_task.cancel()
    try:
        await cleanup_task
    except asyncio.CancelledError:
        _log.info("TTL cleanup task cancelled cleanly.")
    except Exception as e:
        _log.warning(f"TTL cleanup task shutdown error: {e}")

    # 2. Close Motor async client
    close_motor_client()

    # 3. Close sync pymongo client
    close_connection()

    _log.info("Server shutdown complete.")


from config.settings import settings

app = FastAPI(
    title="OrbitAvanya Backend API",
    version="2.0",
    description="AI-powered tender intelligence, company research, and proposal generation platform using MySQL.",
    lifespan=lifespan,
)

# Enable CORS for frontend connectivity
allowed_cors_origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:5050",
    "http://127.0.0.1:5050",
]
for origin in list(getattr(settings, "CORS_ORIGINS", [])):
    if origin and origin not in allowed_cors_origins:
        allowed_cors_origins.append(origin)
if settings.CLIENT_URL:
    client_origin = settings.CLIENT_URL.rstrip("/")
    if client_origin not in allowed_cors_origins:
        allowed_cors_origins.append(client_origin)
if settings.API_BASE_URL:
    api_origin = settings.API_BASE_URL.rstrip("/")
    if api_origin not in allowed_cors_origins:
        allowed_cors_origins.append(api_origin)


app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_cors_origins,
    allow_origin_regex=r"https?://(localhost|127\.0\.0\.1)(:\d+)?",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["Authorization", "Content-Type", "X-Requested-With", "Accept"],
)

@app.middleware('http')
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    response.headers['Permissions-Policy'] = 'camera=(), microphone=(), geolocation=()'
    return response


# ---------------------------------------------------------------------------
# Dev Diagnostic Middleware — ONLY active when DEBUG_LOGIN_DIAGNOSTIC=true
# Disabled in production automatically (debug defaults to False in settings).
# ---------------------------------------------------------------------------
if getattr(settings, "DEBUG_LOGIN_DIAGNOSTIC", False):
    @app.middleware("http")
    async def log_login_requests(request: Request, call_next):
        if request.method == "POST" and request.url.path == "/api/auth/login":
            body_bytes = await request.body()
            async def receive():
                return {"type": "http.request", "body": body_bytes, "more_body": False}
            request._receive = receive

            try:
                import json
                payload = json.loads(body_bytes.decode("utf-8"))
                email = payload.get("email", "")
                password = payload.get("password", "")
                _log.debug(f"[DIAGNOSTIC] Login request: email={email!r}, password_len={len(password)}")

                from utils.db_client import _mysql_available
                if _mysql_available:
                    def _diag_check():
                        import bcrypt as _bcrypt
                        from utils.db_client import get_sync_db_session
                        from models.sql_models import User as SQLUser
                        from sqlalchemy import select
                        with get_sync_db_session() as db:
                            user = db.execute(
                                select(SQLUser).where(SQLUser.email == email.lower().strip())
                            ).scalar_one_or_none()
                            if not user:
                                _log.debug(f"[DIAGNOSTIC] User {email!r} NOT found in database")
                            else:
                                hashed = str(user.password_hash or "")
                                is_valid = _bcrypt.checkpw(password.encode(), hashed.encode()) if hashed else False
                                _log.debug(
                                    f"[DIAGNOSTIC] User found, is_verified={user.is_verified}, "
                                    f"role={user.role}, bcrypt_match={is_valid}"
                                )
                    await asyncio.to_thread(_diag_check)

            except Exception as e:
                _log.debug(f"[DIAGNOSTIC] Login diagnostics error: {e}")

        return await call_next(request)



# ---------------------------------------------------------------------------
# Global error logging
# ---------------------------------------------------------------------------
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from utils.helpers import setup_logger as _setup_logger

_error_logger = _setup_logger("server.errors")


def _add_cors_headers(response: JSONResponse, request: Request) -> JSONResponse:
    origin = request.headers.get("origin")
    if origin:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Credentials"] = "true"
        response.headers["Access-Control-Allow-Methods"] = "*"
        response.headers["Access-Control-Allow-Headers"] = "*"
    return response


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    if exc.status_code >= 500:
        _error_logger.error(
            f"HTTP {exc.status_code} on {request.method} {request.url.path}: {exc.detail}",
            exc_info=True,
            extra={"path": str(request.url.path), "method": request.method, "status_code": exc.status_code},
        )
    res = JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
        headers=getattr(exc, "headers", None),
    )
    return _add_cors_headers(res, request)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    res = JSONResponse(status_code=422, content={"detail": exc.errors()})
    return _add_cors_headers(res, request)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    _error_logger.error(
        f"Unhandled exception on {request.method} {request.url.path}: {exc}",
        exc_info=True,
        extra={"path": str(request.url.path), "method": request.method, "status_code": 500},
    )
    res = JSONResponse(
        status_code=500,
        content={"detail": "Internal server error. Our team has been notified."},
    )
    return _add_cors_headers(res, request)



# ---- Register all routers ----
app.include_router(auth_router, prefix="/api")
app.include_router(users_router, prefix="/api")
app.include_router(tasks_router, prefix="/api")
app.include_router(meetings_router, prefix="/api")
app.include_router(notifications_router, prefix="/api")
app.include_router(integrations_router, prefix="/api")
app.include_router(companies_router, prefix="/api")
app.include_router(people_router, prefix="/api")
app.include_router(reports_router, prefix="/api")
app.include_router(proposals_router, prefix="/api")
app.include_router(tenders_router, prefix="/api")
app.include_router(rfp_respond_router, prefix="/api")
app.include_router(templates_router, prefix="/api")
app.include_router(preview_router, prefix="/api")
app.include_router(analytics_router, prefix="/api")
app.include_router(naics_router, prefix="/api")
app.include_router(sic_router, prefix="/api")
app.include_router(system_logs_router, prefix="/api")

# Serve downloaded tender documents statically
from pathlib import Path
from fastapi.staticfiles import StaticFiles

_downloads_dir = Path("downloads")
_downloads_dir.mkdir(parents=True, exist_ok=True)
app.mount("/downloads", StaticFiles(directory=str(_downloads_dir)), name="downloads")


@app.get("/")
@app.get("/api")
@app.get("/api/")
def get_api_root():
    return {
        "status": "online",
        "service": "OrbitAvanya API v2.0",
        "health": "/api/health",
        "documentation": "/docs"
    }


@app.get("/health")
@app.get("/api/health")
async def health():
    """Health check. Pings both MongoDB and MySQL."""
    mongo_status = "unhealthy"
    try:
        from utils.db_client import get_async_db
        db = get_async_db()
        await db.command("ping")
        mongo_status = "healthy"
    except Exception as e:
        _log.error(f"MongoDB health check failed: {e}")

    mysql_status = "unhealthy"
    if _mysql_available:
        try:
            from utils.db_client import ping_mysql
            if await ping_mysql():
                mysql_status = "healthy"
        except Exception as e:
            _log.error(f"MySQL health check failed: {e}")

    return {
        "ok": mysql_status == "healthy",
        "service": "OrbitAvanya API v2.0",
        "dependencies": {
            "mongodb": mongo_status,
            "mysql": mysql_status
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

    if sys.platform == "win32":
        try:
            import watchfiles  # noqa: F401  # if installed, uvicorn uses it automatically
        except ImportError:
            if reload_enabled:
                import logging as _log_tmp
                _log_tmp.getLogger("server").warning(
                    "[Windows] Hot-reload disabled because 'watchfiles' is not installed. "
                    "StatReload (subprocess-based) cannot share the ProactorEventLoop "
                    "needed by Playwright. Run `uv add watchfiles` to re-enable hot-reload."
                )
                reload_enabled = False

    host = (
        "0.0.0.0"
        if (settings.CODESPACES or os.getenv("CODESPACES") == "true")
        else "127.0.0.1"
    )
    loop_config = "server:proactor_loop_factory" if sys.platform == "win32" else "auto"
    uvicorn.run(
        "server:app",
        host=host,
        port=settings.PORT,
        reload=reload_enabled,
        timeout_keep_alive=600,
        loop=loop_config,
    )