"""
utils/db_client.py
------------------
MongoDB connection management for the entire PPT-Agent application.

Dual-access pattern:
  - Async Motor client  → FastAPI routes and async core modules
  - Sync pymongo client → CLI scripts, pipeline workers, tests

Usage (async — FastAPI routes):
    from utils.db_client import get_async_collection
    col = get_async_collection("users")
    user = await col.find_one({"email": email})

Usage (sync — scripts / pipeline):
    from utils.db_client import get_collection
    col = get_collection("raw_linkedin")
    doc = col.find_one({"company_slug": "acme"})
"""

from __future__ import annotations

import re
from typing import Optional, Any

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


def ensure_all_indexes() -> None:
    """
    Creates indexes for ALL collections across the application.
    Safe to call repeatedly — only creates indexes that don't exist.
    """
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

    logger.info("All indexes ensured (25+ collections).")


# ---------------------------------------------------------------------------
# Task status helpers (sync — used by background threads/scripts)
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
    """Upsert background task progress/status into MongoDB."""
    from datetime import datetime, timezone, timedelta
    col = get_collection("task_statuses")
    now = datetime.now(timezone.utc)
    doc: dict[str, Any] = {
        "task_id": task_id,
        "type": task_type,
        "progress": progress,
        "status": status,
        "message": message,
        "updatedAt": now,
        "expireAt": now + timedelta(days=1),
    }
    if filename is not None:
        doc["filename"] = filename
    if extra:
        doc.update(extra)
    try:
        col.update_one({"task_id": task_id}, {"$set": doc}, upsert=True)
    except PyMongoError as e:
        logger.error(f"Failed to update task status for {task_id}: {e}")


def get_task_status_db(task_id: str) -> Optional[dict]:
    """Retrieve background task status from MongoDB by task_id."""
    col = get_collection("task_statuses")
    return col.find_one({"task_id": task_id}, {"_id": 0, "expireAt": 0, "updatedAt": 0})


def get_all_task_statuses_db() -> list[dict]:
    """Retrieve all background task statuses from MongoDB."""
    col = get_collection("task_statuses")
    return list(col.find({}, {"_id": 0, "expireAt": 0, "updatedAt": 0}))


# ---------------------------------------------------------------------------
# Async task status helpers (Motor — used by async routes)
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
    """Async version of update_task_status for use in async FastAPI routes."""
    from datetime import datetime, timezone, timedelta
    col = get_async_collection("task_statuses")
    now = datetime.now(timezone.utc)
    doc: dict[str, Any] = {
        "task_id": task_id,
        "type": task_type,
        "progress": progress,
        "status": status,
        "message": message,
        "updatedAt": now,
        "expireAt": now + timedelta(days=1),
    }
    if filename is not None:
        doc["filename"] = filename
    if extra:
        doc.update(extra)
    try:
        await col.update_one({"task_id": task_id}, {"$set": doc}, upsert=True)
    except Exception as e:
        logger.error(f"[motor] Failed to update task status for {task_id}: {e}")


async def get_task_status_async(task_id: str) -> Optional[dict]:
    """Async version of get_task_status_db for use in async FastAPI routes."""
    col = get_async_collection("task_statuses")
    return await col.find_one({"task_id": task_id}, {"_id": 0, "expireAt": 0, "updatedAt": 0})
