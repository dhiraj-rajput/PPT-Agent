"""
app/routes/system_logs.py
--------------------------
Admin-only "Server Logs" endpoints — using MySQL.
"""

from __future__ import annotations

import asyncio
import os
import json
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import AsyncGenerator, Optional, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from app.core.auth import require_admin
from utils.db_client import get_db_session, _mysql_available
from models.sql_models import (
    ErrorLog as SQL_ErrorLog,
    User as SQLUser,
)
from sqlalchemy import select, update, insert, delete, func, or_, and_, desc

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/system-logs", tags=["system-logs"])

VALID_LEVELS = {"WARNING", "ERROR", "CRITICAL"}

_LOG_FILE = Path(__file__).resolve().parent.parent.parent / "logs" / "app.log"


def _iso(dt: Any) -> Optional[str]:
    return dt.isoformat() if dt and hasattr(dt, "isoformat") else None


async def _require_admin_sse(
    request: Request,
    token: Optional[str] = Query(None, description="JWT token for SSE"),
) -> dict:
    from jose import JWTError, jwt as _jwt
    from config.settings import settings as _settings

    exc = HTTPException(
        status_code=401,
        detail="Not authenticated or token expired.",
    )

    auth_header = request.headers.get("Authorization", "")
    resolved_token = None
    if auth_header.startswith("Bearer "):
        resolved_token = auth_header[7:].strip()
    elif token:
        resolved_token = token
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

    if _mysql_available:
        async for db in get_db_session():
            stmt = select(SQLUser).where(SQLUser.id == int(user_id))
            user_obj = (await db.execute(stmt)).scalar_one_or_none()
            if not user_obj:
                raise exc
            if user_obj.role.lower() not in ("admin", "owner"):
                raise HTTPException(status_code=403, detail="Admin access required.")
            return {
                "id": user_obj.id,
                "email": user_obj.email,
                "name": user_obj.name,
                "role": user_obj.role
            }
    raise exc


def _to_public(doc: SQL_ErrorLog) -> dict:
    if not doc:
        return {}
    extra = doc.extra_data or {}
    return {
        "id": str(doc.id),
        "timestamp": _iso(doc.timestamp),
        "level": doc.level or "ERROR",
        "source": doc.source or "",
        "message": doc.message or "",
        "detail": doc.stack_trace or "",
        "path": extra.get("path"),
        "method": extra.get("method"),
        "statusCode": extra.get("statusCode"),
        "userEmail": extra.get("userEmail"),
        "ip": extra.get("ip"),
        "module": extra.get("module"),
        "func": extra.get("func"),
        "line": extra.get("line"),
        "resolved": bool(doc.resolved),
        "resolvedBy": doc.resolved_by,
        "resolvedAt": _iso(doc.resolved_at),
    }


async def _tail_log_file(log_path: Path) -> AsyncGenerator[str, None]:
    BACKFILL_LINES = 100
    HEARTBEAT_SECS = 15
    POLL_INTERVAL = 0.5

    try:
        if log_path.exists():
            with open(log_path, "r", encoding="utf-8", errors="replace") as f:
                try:
                    f.seek(0, 2)
                    file_size = f.tell()
                    f.seek(max(0, file_size - 50_000))
                    tail_lines = f.read().splitlines()[-BACKFILL_LINES:]
                    for line in tail_lines:
                        if line.strip():
                            yield f"data: {line}\n\n"
                except Exception:
                    pass

        last_heartbeat = asyncio.get_event_loop().time()
        with open(log_path, "a+", encoding="utf-8", errors="replace") as f:
            f.seek(0, 2)
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
                        yield ": keepalive\n\n"
                        last_heartbeat = now
                    await asyncio.sleep(POLL_INTERVAL)

    except asyncio.CancelledError:
        return
    except Exception as exc:
        yield f"data: [LOG STREAM ERROR] {exc}\n\n"


@router.get("/stream")
async def stream_logs(_admin: dict = Depends(_require_admin_sse)):
    if not _LOG_FILE.parent.exists():
        _LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    if not _LOG_FILE.exists():
        _LOG_FILE.touch()

    return StreamingResponse(
        _tail_log_file(_LOG_FILE),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            "Content-Encoding": "none",
            "Access-Control-Allow-Origin": "*",
        },
    )


@router.get("")
async def list_logs(
    level: Optional[str] = Query(None, description="Comma-separated levels"),
    resolved: Optional[bool] = Query(None),
    q: Optional[str] = Query(None, description="Search text"),
    source: Optional[str] = Query(None),
    since: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(25, ge=1, le=200),
    _admin: dict = Depends(require_admin),
):
    logs = []
    total = 0

    if _mysql_available:
        try:
            async for db in get_db_session():
                filter_conditions = []
                if level:
                    levels = [lvl.strip().upper() for lvl in level.split(",") if lvl.strip().upper() in VALID_LEVELS]
                    if levels:
                        filter_conditions.append(SQL_ErrorLog.level.in_(levels))

                if resolved is not None:
                    filter_conditions.append(SQL_ErrorLog.resolved == resolved)

                if source:
                    filter_conditions.append(SQL_ErrorLog.source.ilike(f"%{source.strip()}%"))

                if since:
                    try:
                        since_dt = datetime.fromisoformat(since.replace("Z", "+00:00"))
                        if since_dt.tzinfo:
                            since_dt = since_dt.astimezone(timezone.utc).replace(tzinfo=None)
                        filter_conditions.append(SQL_ErrorLog.timestamp > since_dt)
                    except ValueError:
                        raise HTTPException(400, "Invalid 'since' timestamp format.")

                if q:
                    qs = f"%{q.strip()}%"
                    filter_conditions.append(or_(
                        SQL_ErrorLog.message.ilike(qs),
                        SQL_ErrorLog.stack_trace.ilike(qs),
                        SQL_ErrorLog.source.ilike(qs)
                    ))

                stmt_count = select(func.count()).select_from(SQL_ErrorLog)
                stmt_select = select(SQL_ErrorLog)
                if filter_conditions:
                    stmt_count = stmt_count.where(and_(*filter_conditions))
                    stmt_select = stmt_select.where(and_(*filter_conditions))

                total = (await db.execute(stmt_count)).scalar() or 0

                skip = (page - 1) * limit
                stmt_select = stmt_select.order_by(desc(SQL_ErrorLog.timestamp)).offset(skip).limit(limit)
                res = await db.execute(stmt_select)
                logs = [_to_public(d) for d in res.scalars().all()]
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(500, f"Database error: {e}")

    return {
        "logs": logs,
        "total": total,
        "page": page,
        "limit": limit,
        "pages": max(1, (total + limit - 1) // limit),
    }


@router.get("/summary")
async def logs_summary(_admin: dict = Depends(require_admin)):
    total = 0
    unresolved = 0
    critical = 0
    errors = 0
    warnings = 0
    last_24h_count = 0
    last_7d_count = 0
    latest = None

    now = datetime.utcnow()
    last_24h = now - timedelta(hours=24)
    last_7d = now - timedelta(days=7)

    if _mysql_available:
        try:
            async for db in get_db_session():
                total = (await db.execute(select(func.count()).select_from(SQL_ErrorLog))).scalar() or 0
                unresolved = (await db.execute(select(func.count()).select_from(SQL_ErrorLog).where(SQL_ErrorLog.resolved == False))).scalar() or 0
                critical = (await db.execute(select(func.count()).select_from(SQL_ErrorLog).where(SQL_ErrorLog.level == "CRITICAL", SQL_ErrorLog.resolved == False))).scalar() or 0
                errors = (await db.execute(select(func.count()).select_from(SQL_ErrorLog).where(SQL_ErrorLog.level == "ERROR", SQL_ErrorLog.resolved == False))).scalar() or 0
                warnings = (await db.execute(select(func.count()).select_from(SQL_ErrorLog).where(SQL_ErrorLog.level == "WARNING", SQL_ErrorLog.resolved == False))).scalar() or 0

                last_24h_count = (await db.execute(select(func.count()).select_from(SQL_ErrorLog).where(SQL_ErrorLog.timestamp >= last_24h))).scalar() or 0
                last_7d_count = (await db.execute(select(func.count()).select_from(SQL_ErrorLog).where(SQL_ErrorLog.timestamp >= last_7d))).scalar() or 0

                stmt_latest = select(SQL_ErrorLog).order_by(desc(SQL_ErrorLog.timestamp)).limit(1)
                latest_doc = (await db.execute(stmt_latest)).scalar_one_or_none()
                latest = _to_public(latest_doc) if latest_doc else None
        except Exception as e:
            raise HTTPException(500, f"Database error: {e}")

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
    since: Optional[str] = Query(None),
    _admin: dict = Depends(require_admin),
):
    new_logs = []
    if _mysql_available:
        try:
            async for db in get_db_session():
                filter_conditions = [SQL_ErrorLog.level.in_(["ERROR", "CRITICAL"]), SQL_ErrorLog.resolved == False]
                if since:
                    try:
                        since_dt = datetime.fromisoformat(since.replace("Z", "+00:00"))
                        if since_dt.tzinfo:
                            since_dt = since_dt.astimezone(timezone.utc).replace(tzinfo=None)
                        filter_conditions.append(SQL_ErrorLog.timestamp > since_dt)
                    except ValueError:
                        raise HTTPException(400, "Invalid 'since' timestamp format.")

                stmt = select(SQL_ErrorLog).where(and_(*filter_conditions)).order_by(desc(SQL_ErrorLog.timestamp)).limit(10)
                res = await db.execute(stmt)
                new_logs = [_to_public(d) for d in res.scalars().all()]
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(500, f"Database error: {e}")

    return {"newLogs": new_logs}


@router.patch("/{log_id}/resolve")
async def resolve_log(log_id: str, admin: dict = Depends(require_admin)):
    try:
        lid = int(log_id)
    except ValueError:
        raise HTTPException(400, "Invalid log ID.")

    if _mysql_available:
        try:
            async for db in get_db_session():
                stmt = select(SQL_ErrorLog).where(SQL_ErrorLog.id == lid)
                doc = (await db.execute(stmt)).scalar_one_or_none()
                if not doc:
                    raise HTTPException(404, "Log entry not found.")

                await db.execute(
                    update(SQL_ErrorLog)
                    .where(SQL_ErrorLog.id == lid)
                    .values(
                        resolved=True,
                        resolved_by=admin.get("email") or admin.get("name") or "Admin",
                        resolved_at=datetime.utcnow()
                    )
                )
                await db.commit()

                # refetch
                doc = (await db.execute(select(SQL_ErrorLog).where(SQL_ErrorLog.id == lid))).scalar_one()
                return {"log": _to_public(doc)}
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(500, f"Database error: {e}")
    raise HTTPException(500, "Database is unavailable.")


@router.patch("/{log_id}/unresolve")
async def unresolve_log(log_id: str, _admin: dict = Depends(require_admin)):
    try:
        lid = int(log_id)
    except ValueError:
        raise HTTPException(400, "Invalid log ID.")

    if _mysql_available:
        try:
            async for db in get_db_session():
                stmt = select(SQL_ErrorLog).where(SQL_ErrorLog.id == lid)
                doc = (await db.execute(stmt)).scalar_one_or_none()
                if not doc:
                    raise HTTPException(404, "Log entry not found.")

                await db.execute(
                    update(SQL_ErrorLog)
                    .where(SQL_ErrorLog.id == lid)
                    .values(resolved=False, resolved_by="", resolved_at=None)
                )
                await db.commit()

                # refetch
                doc = (await db.execute(select(SQL_ErrorLog).where(SQL_ErrorLog.id == lid))).scalar_one()
                return {"log": _to_public(doc)}
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(500, f"Database error: {e}")
    raise HTTPException(500, "Database is unavailable.")


@router.delete("/{log_id}")
async def delete_log(log_id: str, _admin: dict = Depends(require_admin)):
    try:
        lid = int(log_id)
    except ValueError:
        raise HTTPException(400, "Invalid log ID.")

    if _mysql_available:
        try:
            async for db in get_db_session():
                stmt = select(SQL_ErrorLog).where(SQL_ErrorLog.id == lid)
                doc = (await db.execute(stmt)).scalar_one_or_none()
                if not doc:
                    raise HTTPException(404, "Log entry not found.")

                await db.execute(delete(SQL_ErrorLog).where(SQL_ErrorLog.id == lid))
                await db.commit()
                return {"ok": True}
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(500, f"Database error: {e}")
    raise HTTPException(500, "Database is unavailable.")


@router.delete("")
async def clear_logs(
    scope: str = Query("resolved", pattern="^(resolved|all)$"),
    _admin: dict = Depends(require_admin),
):
    if _mysql_available:
        try:
            async for db in get_db_session():
                stmt = delete(SQL_ErrorLog)
                if scope != "all":
                    stmt = stmt.where(SQL_ErrorLog.resolved == True)
                res = await db.execute(stmt)
                await db.commit()
                return {"ok": True, "deleted": getattr(res, "rowcount", 0)}

        except Exception as e:
            raise HTTPException(500, f"Database error: {e}")
    raise HTTPException(500, "Database is unavailable.")


@router.post("/test", status_code=201)
async def emit_test_error(admin: dict = Depends(require_admin)):
    try:
        raise RuntimeError("This is a test error triggered manually from the Server Logs page.")
    except RuntimeError:
        logger.error(
            "Test error triggered by admin to verify the logging pipeline.",
            exc_info=True,
            extra={"path": "/api/system-logs/test", "method": "POST", "status_code": 201, "user_email": admin.get("email")},
        )
    return {"ok": True, "message": "Test error logged. It should appear in the list within a few seconds."}
