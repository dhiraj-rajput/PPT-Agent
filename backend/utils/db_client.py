"""
utils/db_client.py
------------------
Dual-DB connection management: MongoDB (Motor + pymongo) AND MySQL (SQLAlchemy 2.x async).

MongoDB patterns (unchanged — existing code continues to work):
  - Async Motor client  → FastAPI routes and async core modules
  - Sync pymongo client → CLI scripts, pipeline workers, tests

MySQL patterns (new — used for all relational/flat collections):
  - get_db_session()      → FastAPI async dependency (yields AsyncSession)
  - get_sync_db_session() → sync context manager for scripts/workers
  - init_mysql()          → create all tables at startup

Usage (async — FastAPI routes):
    from utils.db_client import get_async_collection  # MongoDB (document store)
    from utils.mysql_client import get_db_session     # MySQL (relational)

    col = get_async_collection("raw_linkedin")
    doc = await col.find_one({"company_slug": "acme"})

    async with get_db_session() as db:
        result = await db.execute(select(User).where(User.email == email))

Usage (sync — scripts / pipeline):
    from utils.db_client import get_collection            # MongoDB
    from utils.mysql_client import get_sync_db_session   # MySQL
"""

import json
import re
from typing import Optional, Any
import threading

import pymongo
from pymongo import MongoClient
from pymongo.collection import Collection
from pymongo.database import Database
from pymongo.errors import PyMongoError

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase, AsyncIOMotorCollection

from config.settings import settings
from utils.helpers import setup_logger

logger = setup_logger(__name__)


def _is_tls_uri(uri: str) -> bool:
    clean_uri = uri.lower()
    return clean_uri.startswith("mongodb+srv://") or "tls=true" in clean_uri or "ssl=true" in clean_uri


# ---------------------------------------------------------------------------
# Sync singleton (scripts, pipeline, tests)
# ---------------------------------------------------------------------------

_mongo_client: Optional[MongoClient] = None
_mongo_database: Optional[Database] = None


def get_database() -> Database:
    """Returns the singleton sync pymongo database. Lazy-initialised on first call."""
    global _mongo_client, _mongo_database

    if _mongo_database is not None:
        return _mongo_database

    redacted_uri = re.sub(r"://[^@]*@", "://***:***@", settings.MONGO_URI)
    logger.info(f"[sync] Connecting to MongoDB at: {redacted_uri}")

    client_kwargs: dict[str, Any] = {
        "serverSelectionTimeoutMS": 5000,
        "connectTimeoutMS": 5000,
        "socketTimeoutMS": 10000,
        "maxPoolSize": 20,
        "minPoolSize": 2,
    }
    if _is_tls_uri(settings.MONGO_URI):
        try:
            import certifi
            client_kwargs["tlsCAFile"] = certifi.where()
        except Exception:
            pass

    _mongo_client = MongoClient(
        settings.MONGO_URI,
        **client_kwargs
    )
    _mongo_client.admin.command("ping")
    logger.info(f"[sync] MongoDB connected. DB: '{settings.MONGO_DB_NAME}'")

    _mongo_database = _mongo_client[settings.MONGO_DB_NAME]
    return _mongo_database


def get_collection(collection_name: str) -> Collection:
    """Returns a sync pymongo Collection. Use in scripts and pipeline workers."""
    return get_database()[collection_name]


def close_connection() -> None:
    """Closes the sync MongoDB connection. Call on CLI/script shutdown."""
    global _mongo_client, _mongo_database
    if _mongo_client:
        logger.info("[sync] Closing MongoDB connection.")
        _mongo_client.close()
        _mongo_client = None
        _mongo_database = None


# ---------------------------------------------------------------------------
# Async Motor singleton (FastAPI routes and async core modules)
# ---------------------------------------------------------------------------

from utils.mysql_client import (
    get_sync_db_session,
    get_db_session,
)



_mysql_available = True


_motor_client: Optional[AsyncIOMotorClient] = None
_motor_database: Optional[AsyncIOMotorDatabase] = None


def get_motor_client() -> AsyncIOMotorClient:
    """
    Returns the Motor async client singleton.
    Lazy-initialises if not already initialised.
    """
    global _motor_client
    if _motor_client is None:
        init_motor_client()
    assert _motor_client is not None
    return _motor_client


def init_motor_client() -> AsyncIOMotorClient:
    """
    Create the async Motor client singleton.
    Must be called once in the FastAPI lifespan startup handler or lazy-initialised.
    Returns the client so the caller can store it for shutdown.
    """
    global _motor_client, _motor_database

    redacted_uri = re.sub(r"://[^@]*@", "://***:***@", settings.MONGO_URI)
    logger.info(f"[motor] Connecting to MongoDB at: {redacted_uri}")

    motor_kwargs: dict[str, Any] = {
        "serverSelectionTimeoutMS": 5000,
        "connectTimeoutMS": 5000,
        "socketTimeoutMS": 30000,
        "maxPoolSize": 50,
        "minPoolSize": 5,
    }
    if _is_tls_uri(settings.MONGO_URI):
        try:
            import certifi
            motor_kwargs["tlsCAFile"] = certifi.where()
        except Exception:
            pass

    _motor_client = AsyncIOMotorClient(
        settings.MONGO_URI,
        **motor_kwargs
    )
    _motor_database = _motor_client[settings.MONGO_DB_NAME]
    logger.info(f"[motor] Motor async client ready. DB: '{settings.MONGO_DB_NAME}'")
    assert _motor_client is not None
    return _motor_client


def close_motor_client() -> None:
    """Closes the async Motor client. Call in FastAPI lifespan shutdown."""
    global _motor_client, _motor_database
    if _motor_client:
        logger.info("[motor] Closing Motor async client.")
        _motor_client.close()
        _motor_client = None
        _motor_database = None


def get_async_db() -> AsyncIOMotorDatabase:
    """Returns the Motor async database. Lazy-initialises if not already initialised."""
    global _motor_database
    if _motor_database is None:
        init_motor_client()
    assert _motor_database is not None
    return _motor_database


def get_async_collection(collection_name: str) -> AsyncIOMotorCollection:
    """
    Returns a Motor async Collection. Use in FastAPI async routes.

    Example:
        col = get_async_collection("users")
        user = await col.find_one({"email": email})
    """
    return get_async_db()[collection_name]


# ---------------------------------------------------------------------------
# Index management
# ---------------------------------------------------------------------------

def ensure_indexes() -> None:
    """Creates core LinkedIn pipeline indexes (sync, for script use)."""
    logger.info("Ensuring core MongoDB indexes...")

    try:
        raw_linkedin = get_collection("raw_linkedin")
        raw_linkedin.create_index(
            [("company_slug", pymongo.ASCENDING), ("scrape_layer", pymongo.ASCENDING)],
            name="idx_raw_linkedin_slug_scrape_layer",
        )
        raw_linkedin.create_index(
            [("company_slug", pymongo.ASCENDING), ("scrape_layer", pymongo.ASCENDING), ("scraped_at", pymongo.DESCENDING)],
            name="idx_raw_linkedin_slug_layer_time",
        )

        get_collection("structured_linkedin").create_index(
            [("company_slug", pymongo.ASCENDING)],
            name="idx_structured_linkedin_slug",
            unique=True,
        )

        get_collection("scrape_logs").create_index(
            [("company_slug", pymongo.ASCENDING), ("scraped_at", pymongo.DESCENDING)],
            name="idx_scrape_logs_slug_time",
        )
        logger.info("Core indexes ensured.")
    except PyMongoError as e:
        logger.warning(f"MongoDB core index setup note: {e}")


_indexes_ensured_flag = False
_indexes_lock = threading.Lock()

def ensure_all_indexes() -> None:
    """Idempotent sync startup task to create MongoDB indexes."""
    global _indexes_ensured_flag
    with _indexes_lock:
        if _indexes_ensured_flag:
            return
        _indexes_ensured_flag = True

    logger.info("Creating indexes for all collections...")

    ensure_indexes()


    def _safe_create(col_name: str, keys: list, **kwargs):
        try:
            get_collection(col_name).create_index(keys, **kwargs)
        except Exception:
            pass

    # Website pipeline
    _safe_create("raw_website", [("company_slug", pymongo.ASCENDING), ("scraped_at", pymongo.DESCENDING)], name="idx_raw_website_slug_time")
    _safe_create("structured_website", [("company_slug", pymongo.ASCENDING)], name="idx_structured_website_slug", unique=True)

    # Search & profiles
    _safe_create("search_cache", [("query", pymongo.ASCENDING)], name="idx_search_cache_query", unique=True)
    _safe_create("company_profiles", [("company_slug", pymongo.ASCENDING)], name="idx_company_profiles_slug", unique=True)

    # External search
    _safe_create("raw_external_search", [("company_slug", pymongo.ASCENDING), ("scraped_at", pymongo.DESCENDING)], name="idx_raw_external_search_slug_time")
    _safe_create("structured_external_search", [("company_slug", pymongo.ASCENDING)], name="idx_structured_external_search_slug", unique=True)

    # Task & OAuth state TTL
    _safe_create("task_statuses", [("task_id", pymongo.ASCENDING)], name="idx_task_statuses_id", unique=True)
    _safe_create("task_statuses", [("expireAt", pymongo.ASCENDING)], name="idx_task_statuses_expire_at", expireAfterSeconds=0)
    _safe_create("oauth_states", [("state", pymongo.ASCENDING)], name="idx_oauth_states_id", unique=True)
    _safe_create("oauth_states", [("expireAt", pymongo.ASCENDING)], name="idx_oauth_states_expire_at", expireAfterSeconds=0)

    # RFPs & tenders
    _safe_create("rfps", [("solicitation_number", pymongo.ASCENDING)], name="idx_rfps_solicitation_number", unique=True)
    _safe_create("tenders", [("noticeId", pymongo.ASCENDING)], name="idx_tenders_notice_id")
    _safe_create("tenders", [("closing_date", pymongo.ASCENDING), ("status", pymongo.ASCENDING)], name="idx_tenders_closing_status")

    # Leads & campaigns
    _safe_create("leads", [("createdBy", pymongo.ASCENDING)], name="idx_leads_created_by")
    _safe_create("leads", [("campaignId", pymongo.ASCENDING), ("updatedAt", pymongo.DESCENDING)], name="idx_leads_campaign_updated")
    _safe_create("leads", [("campaignId", pymongo.ASCENDING), ("status", pymongo.ASCENDING), ("send_after", pymongo.ASCENDING)], name="idx_leads_campaign_status_send_after")
    _safe_create("leads", [("email", pymongo.ASCENDING), ("status", pymongo.ASCENDING)], name="idx_leads_email_status")
    _safe_create("campaigns", [("status", pymongo.ASCENDING)], name="idx_campaigns_status")

    # Integrations
    _safe_create("integrations", [("service", pymongo.ASCENDING), ("userId", pymongo.ASCENDING)], name="idx_integrations_service_user")

    # Competitor profiles
    _safe_create("competitor_profiles", [("company_name", pymongo.ASCENDING)], name="idx_competitor_profiles_name", collation={"locale": "en", "strength": 2})

    # Company catalog
    _safe_create("company_catalog", [("category", pymongo.ASCENDING)], name="idx_company_catalog_category")

    # Server error logs (admin Server Logs page)
    _safe_create("error_logs", [("timestamp", pymongo.DESCENDING)], name="idx_error_logs_timestamp")
    _safe_create("error_logs", [("level", pymongo.ASCENDING), ("timestamp", pymongo.DESCENDING)], name="idx_error_logs_level_timestamp")
    _safe_create("error_logs", [("resolved", pymongo.ASCENDING), ("timestamp", pymongo.DESCENDING)], name="idx_error_logs_resolved_timestamp")
    # Auto-expire error logs after 30 days to keep the collection lean.
    _safe_create("error_logs", [("timestamp", pymongo.ASCENDING)], name="idx_error_logs_ttl", expireAfterSeconds=60 * 60 * 24 * 30)

    logger.info("All indexes ensured (25+ collections).")


# ---------------------------------------------------------------------------
# MySQL passthrough helpers (thin wrappers around mysql_client)
# ---------------------------------------------------------------------------
# Import here so callers can do: `from utils.db_client import get_db_session`
# while also being able to use: `from utils.mysql_client import get_db_session`
# Both work identically.

try:
    from utils.mysql_client import (  # noqa: F401 — re-exported for convenience
        get_db_session as get_db_session,
        get_sync_db_session as get_sync_db_session,
        init_mysql as init_mysql,
        ping_mysql as ping_mysql,
        ping_mysql_sync as ping_mysql_sync,
    )
    _mysql_available = True
except ImportError:
    _mysql_available = False


def close_mysql() -> None:
    """Dispose the MySQL async engine. Call in FastAPI lifespan shutdown."""
    if not _mysql_available:
        return
    try:
        from utils.mysql_client import _get_async_engine
        engine = _get_async_engine()
        if engine:
            import asyncio
            try:
                loop = asyncio.get_event_loop()
                loop.run_until_complete(engine.dispose())
            except RuntimeError:
                pass  # No running loop — safe to ignore
    except Exception as exc:
        logger.warning(f"[mysql] close_mysql() error: {exc}")


# ---------------------------------------------------------------------------
# Task status helpers (MySQL only)
# ---------------------------------------------------------------------------


def update_task_status(
    task_id: str,
    task_type: str,
    progress: int,
    status: str,
    message: str,
    filename: Optional[str] = None,
    extra: Optional[dict] = None,
) -> None:
    """
    Upsert background task progress/status.
    MySQL task_statuses table only.
    """
    from datetime import datetime, timezone

    if _mysql_available:
        try:
            from sqlalchemy import text
            with get_sync_db_session() as db:
                result_dict: dict[str, Any] = {
                    "task_id": task_id,
                    "task_type": task_type,
                    "status": status,
                    "progress": progress,
                    "message": message,
                    "last_updated": datetime.now(timezone.utc),
                }
                if extra:
                    result_dict["result"] = extra
                db.execute(
                    text(
                        "INSERT INTO task_statuses (task_id, task_type, status, progress, message, last_updated, result, created_at) "
                        "VALUES (:task_id, :task_type, :status, :progress, :message, :last_updated, :result, :created_at) "
                        "ON DUPLICATE KEY UPDATE task_type=VALUES(task_type), status=VALUES(status), progress=VALUES(progress), "
                        "message=VALUES(message), last_updated=VALUES(last_updated), result=VALUES(result)"
                    ),
                    {
                        **result_dict,
                        "result": json.dumps(extra or {}, default=str),
                        "created_at": datetime.now(timezone.utc),
                    },
                )
        except Exception as e:
            logger.error(f"[mysql] update_task_status MySQL failed: {e}")


def get_task_status_db(task_id: str) -> Optional[dict]:
    """
    Retrieve background task status by task_id.
    MySQL only.
    """
    if _mysql_available:
        try:
            from sqlalchemy import text
            with get_sync_db_session() as db:
                row = db.execute(
                    text("SELECT task_id, task_type, status, progress, message, result FROM task_statuses WHERE task_id = :tid"),
                    {"tid": task_id},
                ).mappings().first()
                if row:
                    return dict(row)
        except Exception as e:
            logger.error(f"[mysql] get_task_status_db MySQL failed: {e}")
    return None


def get_all_task_statuses_db() -> list[dict]:
    """
    Retrieve all background task statuses.
    MySQL only.
    """
    if _mysql_available:
        try:
            from sqlalchemy import text
            with get_sync_db_session() as db:
                rows = db.execute(
                    text("SELECT task_id, task_type, status, progress, message, result, created_at FROM task_statuses ORDER BY created_at DESC")
                ).mappings().all()
                return [dict(r) for r in rows]
        except Exception as e:
            logger.error(f"[mysql] get_all_task_statuses_db MySQL failed: {e}")
    return []


# ---------------------------------------------------------------------------
# Async task status helpers (MySQL only)
# ---------------------------------------------------------------------------

async def update_task_status_async(
    task_id: str,
    task_type: str,
    progress: int,
    status: str,
    message: str,
    filename: Optional[str] = None,
    extra: Optional[dict] = None,
) -> None:
    """
    Async upsert of background task progress/status.
    MySQL only.
    """
    from datetime import datetime, timezone

    if _mysql_available:
        try:
            from sqlalchemy import text
            async for db in get_db_session():
                await db.execute(
                    text(
                        "INSERT INTO task_statuses (task_id, task_type, status, progress, message, last_updated, result, created_at) "
                        "VALUES (:task_id, :task_type, :status, :progress, :message, :last_updated, :result, :created_at) "
                        "ON DUPLICATE KEY UPDATE task_type=VALUES(task_type), status=VALUES(status), progress=VALUES(progress), "
                        "message=VALUES(message), last_updated=VALUES(last_updated), result=VALUES(result)"
                    ),
                    {
                        "task_id": task_id,
                        "task_type": task_type,
                        "status": status,
                        "progress": progress,
                        "message": message,
                        "last_updated": datetime.now(timezone.utc),
                        "result": json.dumps(extra or {}, default=str),
                        "created_at": datetime.now(timezone.utc),
                    },
                )
        except Exception as e:
            logger.error(f"[mysql] update_task_status_async MySQL failed: {e}")


async def get_task_status_async(task_id: str) -> Optional[dict]:
    """
    Async get task status. MySQL only.
    """
    if _mysql_available:
        try:
            from sqlalchemy import text
            async for db in get_db_session():
                row = (await db.execute(
                    text("SELECT task_id, status, progress, message, result FROM task_statuses WHERE task_id = :tid"),
                    {"tid": task_id},
                )).mappings().first()
                if row:
                    return dict(row)
        except Exception as e:
            logger.error(f"[mysql] get_task_status_async MySQL failed: {e}")
    return None
