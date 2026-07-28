"""
app/routes/system_logs.py
--------------------------
Admin-only "Server Logs" endpoints.

Every WARNING/ERROR/CRITICAL logged anywhere in the backend (via
utils.helpers.setup_logger) is persisted to the `error_logs` MongoDB
collection by utils.helpers.MongoErrorLogHandler. These endpoints expose
that collection to the frontend Server Logs admin page:

  GET    /api/system-logs                 — paginated, filterable log list
  GET    /api/system-logs/summary         — counts for the dashboard cards
  GET    /api/system-logs/poll            — lightweight "is there anything new"
                                             check, used to drive the live
                                             top-of-app alert banner
  GET    /api/system-logs/stream          — SSE live tail of backend/logs/app.log
                                             (real-time stdout/INFO lines)
  PATCH  /api/system-logs/{id}/resolve    — mark one entry resolved
  PATCH  /api/system-logs/{id}/unresolve  — reopen a resolved entry
  DELETE /api/system-logs/{id}            — delete one entry
  DELETE /api/system-logs                 — bulk clear (resolved only, or all)
  POST   /api/system-logs/test            — emit a synthetic error, useful to
                                             verify the pipeline end-to-end
                                             after a deploy
"""

from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import AsyncGenerator, Optional

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pymongo import DESCENDING

from app.core.auth import require_admin
from utils.db_client import get_async_collection
from utils.helpers import setup_logger

logger = setup_logger(__name__)

router = APIRouter(prefix="/system-logs", tags=["system-logs"])

VALID_LEVELS = {"WARNING", "ERROR", "CRITICAL"}

# Path to the rolling log file written by helpers.setup_logger
_LOG_FILE = Path(__file__).resolve().parent.parent.parent / "logs" / "app.log"


async def _require_admin_sse(
    request: Request,
    token: Optional[str] = Query(None, description="JWT token (for SSE EventSource which cannot send headers)"),
) -> dict:
    """
    Auth dependency for SSE endpoints.
    EventSource (browser SSE) cannot set custom headers, so we accept the
    JWT as a ?token= query parameter in addition to the Authorization header.
    This is safe because: SSE is read-only, the connection is over HTTPS,
    and the token still expires normally.
    """
    from jose import JWTError, jwt as _jwt
    from config.settings import settings as _settings

    exc = HTTPException(
        status_code=401,
        detail="Not authenticated or token expired.",
        headers={"WWW-Authenticate": "Bearer"},
    )

    # 1. Try Authorization: Bearer header first
    auth_header = request.headers.get("Authorization", "")
    resolved_token = None
    if auth_header.startswith("Bearer "):
        resolved_token = auth_header[7:].strip()
    # 2. Fall back to ?token= query parameter (needed for EventSource)
    elif token:
        resolved_token = token
    # 3. Cookie fallback
    else:
        resolved_token = request.cookies.get("orbitavanya_token")

    if not resolved_token:
        raise exc

    try:
        payload = _jwt.decode(resolved_token, _settings.JWT_SECRET, algorithms=["HS256"])
        user_id = payload.get("sub", "")
        if not user_id:
            raise exc
    except JWTError:
        raise exc

    users_col = get_async_collection("users")
    user = await users_col.find_one({"_id": ObjectId(user_id)})
    if not user:
        raise exc

    if user.get("role", "").lower() not in ("admin", "owner"):
        raise HTTPException(status_code=403, detail="Admin access required.")

    return user


def _to_public(doc: dict) -> dict:
    return {
        "id": str(doc["_id"]),
        "timestamp": doc.get("timestamp"),
        "level": doc.get("level", "ERROR"),
        "source": doc.get("source", ""),
        "message": doc.get("message", ""),
        "detail": doc.get("detail", ""),
        "path": doc.get("path"),
        "method": doc.get("method"),
        "statusCode": doc.get("statusCode"),
        "userEmail": doc.get("userEmail"),
        "ip": doc.get("ip"),
        "module": doc.get("module"),
        "func": doc.get("func"),
        "line": doc.get("line"),
        "resolved": doc.get("resolved", False),
        "resolvedBy": doc.get("resolvedBy"),
        "resolvedAt": doc.get("resolvedAt"),
    }


def _oid(log_id: str) -> ObjectId:
    try:
        return ObjectId(log_id)
    except InvalidId:
        raise HTTPException(400, "Invalid log ID.")


# ---------------------------------------------------------------------------
# SSE live log stream — tails backend/logs/app.log in real time
# ---------------------------------------------------------------------------

async def _tail_log_file(log_path: Path) -> AsyncGenerator[str, None]:
    """
    Async generator that tails a log file, yielding new lines as SSE events.

    Falls back to sending heartbeat comments when no new lines arrive,
    which keeps the connection alive through Apache's proxy timeout
    (and avoids the 504 Gateway Timeout on cPanel).
    """
    # Send the last N lines as initial backfill so the page isn't blank
    BACKFILL_LINES = 100
    HEARTBEAT_SECS = 15   # Apache ProxyTimeout keepalive
    POLL_INTERVAL  = 0.5  # seconds between inode checks

    try:
        if log_path.exists():
            with open(log_path, "r", encoding="utf-8", errors="replace") as f:
                # Backfill: seek near end, read last BACKFILL_LINES lines
                try:
                    f.seek(0, 2)  # seek to EOF
                    file_size = f.tell()
                    # Read up to 50 KB from end for backfill
                    f.seek(max(0, file_size - 50_000))
                    tail_lines = f.read().splitlines()[-BACKFILL_LINES:]
                    for line in tail_lines:
                        if line.strip():
                            yield f"data: {line}\n\n"
                except Exception:
                    pass  # backfill best-effort

        # Now tail indefinitely
        last_heartbeat = asyncio.get_event_loop().time()
        with open(log_path, "a+", encoding="utf-8", errors="replace") as f:
            f.seek(0, 2)  # start at EOF
            while True:
                line = f.readline()
                if line:
                    stripped = line.strip()
                    if stripped:
                        yield f"data: {stripped}\n\n"
                    last_heartbeat = asyncio.get_event_loop().time()
                else:
                    now = asyncio.get_event_loop().time()
                    if now - last_heartbeat >= HEARTBEAT_SECS:
                        # SSE comment — keeps connection alive, ignored by clients
                        yield ": keepalive\n\n"
                        last_heartbeat = now
                    await asyncio.sleep(POLL_INTERVAL)

    except asyncio.CancelledError:
        return
    except Exception as exc:
        yield f"data: [LOG STREAM ERROR] {exc}\n\n"


@router.get("/stream")
async def stream_logs(_admin: dict = Depends(_require_admin_sse)):
    """
    SSE endpoint: tails backend/logs/app.log and pushes every new line to
    the browser in real time.  Works through Apache mod_proxy on cPanel via
    the X-Accel-Buffering: no + Cache-Control: no-transform headers.
    """
    if not _LOG_FILE.parent.exists():
        _LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    if not _LOG_FILE.exists():
        _LOG_FILE.touch()

    return StreamingResponse(
        _tail_log_file(_LOG_FILE),
        media_type="text/event-stream",
        headers={
            # Critical for SSE through Apache / cPanel reverse proxy:
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",   # disables Nginx/Apache output buffering
            "Content-Encoding": "none",  # prevents gzip holding back chunks
            "Access-Control-Allow-Origin": "*",
        },
    )


@router.get("")
async def list_logs(
    level: Optional[str] = Query(None, description="Comma-separated: WARNING,ERROR,CRITICAL"),
    resolved: Optional[bool] = Query(None),
    q: Optional[str] = Query(None, description="Free-text search across message/detail/source/path"),
    source: Optional[str] = Query(None),
    since: Optional[str] = Query(None, description="ISO timestamp — only logs after this"),
    page: int = Query(1, ge=1),
    limit: int = Query(25, ge=1, le=200),
    _admin: dict = Depends(require_admin),
):
    col = get_async_collection("error_logs")

    query: dict = {}

    if level:
        levels = [lvl.strip().upper() for lvl in level.split(",") if lvl.strip().upper() in VALID_LEVELS]
        if levels:
            query["level"] = {"$in": levels}

    if resolved is not None:
        query["resolved"] = resolved

    if source:
        query["source"] = {"$regex": source, "$options": "i"}

    if since:
        try:
            since_dt = datetime.fromisoformat(since.replace("Z", "+00:00"))
            query["timestamp"] = {"$gt": since_dt}
        except ValueError:
            raise HTTPException(400, "Invalid 'since' timestamp — use ISO 8601.")

    if q:
        query["$or"] = [
            {"message": {"$regex": q, "$options": "i"}},
            {"detail": {"$regex": q, "$options": "i"}},
            {"source": {"$regex": q, "$options": "i"}},
            {"path": {"$regex": q, "$options": "i"}},
        ]

    total = await col.count_documents(query)
    skip = (page - 1) * limit
    cursor = col.find(query).sort("timestamp", DESCENDING).skip(skip).limit(limit)
    docs = await cursor.to_list(length=limit)

    return {
        "logs": [_to_public(d) for d in docs],
        "total": total,
        "page": page,
        "limit": limit,
        "pages": max(1, (total + limit - 1) // limit),
    }


@router.get("/summary")
async def logs_summary(_admin: dict = Depends(require_admin)):
    col = get_async_collection("error_logs")

    from datetime import timedelta
    now = datetime.now(timezone.utc)
    last_24h = now - timedelta(hours=24)
    last_7d = now - timedelta(days=7)

    total = await col.count_documents({})
    unresolved = await col.count_documents({"resolved": False})
    critical = await col.count_documents({"level": "CRITICAL", "resolved": False})
    errors = await col.count_documents({"level": "ERROR", "resolved": False})
    warnings = await col.count_documents({"level": "WARNING", "resolved": False})
    last_24h_count = await col.count_documents({"timestamp": {"$gte": last_24h}})
    last_7d_count = await col.count_documents({"timestamp": {"$gte": last_7d}})

    latest_doc = await col.find_one({}, sort=[("timestamp", DESCENDING)])
    latest = _to_public(latest_doc) if latest_doc else None

    return {
        "total": total,
        "unresolved": unresolved,
        "critical": critical,
        "errors": errors,
        "warnings": warnings,
        "last24h": last_24h_count,
        "last7d": last_7d_count,
        "latest": latest,
    }


@router.get("/poll")
async def poll_new_errors(
    since: Optional[str] = Query(None, description="ISO timestamp of the last log the client has already seen"),
    _admin: dict = Depends(require_admin),
):
    """
    Lightweight endpoint the frontend polls every few seconds to drive the
    live top-of-app alert banner, without pulling the full paginated list.
    Only reports unresolved ERROR/CRITICAL entries — warnings don't trigger
    an interrupt-style alert.
    """
    col = get_async_collection("error_logs")

    query: dict = {"level": {"$in": ["ERROR", "CRITICAL"]}, "resolved": False}
    if since:
        try:
            since_dt = datetime.fromisoformat(since.replace("Z", "+00:00"))
            query["timestamp"] = {"$gt": since_dt}
        except ValueError:
            raise HTTPException(400, "Invalid 'since' timestamp — use ISO 8601.")

    cursor = col.find(query).sort("timestamp", DESCENDING).limit(10)
    docs = await cursor.to_list(length=10)

    return {"newLogs": [_to_public(d) for d in docs]}


@router.patch("/{log_id}/resolve")
async def resolve_log(log_id: str, admin: dict = Depends(require_admin)):
    col = get_async_collection("error_logs")
    oid = _oid(log_id)

    await col.update_one(
        {"_id": oid},
        {"$set": {
            "resolved": True,
            "resolvedBy": admin.get("email") or admin.get("name") or "Admin",
            "resolvedAt": datetime.now(tz=timezone.utc),
        }},
    )
    doc = await col.find_one({"_id": oid})
    if not doc:
        raise HTTPException(404, "Log entry not found.")
    return {"log": _to_public(doc)}


@router.patch("/{log_id}/unresolve")
async def unresolve_log(log_id: str, _admin: dict = Depends(require_admin)):
    col = get_async_collection("error_logs")
    oid = _oid(log_id)

    await col.update_one(
        {"_id": oid},
        {"$set": {"resolved": False}, "$unset": {"resolvedBy": "", "resolvedAt": ""}},
    )
    doc = await col.find_one({"_id": oid})
    if not doc:
        raise HTTPException(404, "Log entry not found.")
    return {"log": _to_public(doc)}


@router.delete("/{log_id}")
async def delete_log(log_id: str, _admin: dict = Depends(require_admin)):
    col = get_async_collection("error_logs")
    oid = _oid(log_id)

    result = await col.find_one_and_delete({"_id": oid})
    if not result:
        raise HTTPException(404, "Log entry not found.")
    return {"ok": True}


@router.delete("")
async def clear_logs(
    scope: str = Query("resolved", pattern="^(resolved|all)$"),
    _admin: dict = Depends(require_admin),
):
    col = get_async_collection("error_logs")
    query = {} if scope == "all" else {"resolved": True}
    result = await col.delete_many(query)
    return {"ok": True, "deleted": result.deleted_count}


@router.post("/test", status_code=201)
async def emit_test_error(admin: dict = Depends(require_admin)):
    """
    Deliberately logs a synthetic error so an admin can verify — right from
    the Server Logs page — that the logging pipeline (handler → MongoDB →
    API → alert banner) is working end-to-end after a deploy.
    """
    try:
        raise RuntimeError("This is a test error triggered manually from the Server Logs page.")
    except RuntimeError:
        logger.error(
            f"Test error triggered by admin {admin.get('email', 'unknown')} to verify the logging pipeline.",
            exc_info=True,
            extra={"path": "/api/system-logs/test", "method": "POST", "status_code": 201, "user_email": admin.get("email")},
        )
    return {"ok": True, "message": "Test error logged. It should appear in the list within a few seconds."}
