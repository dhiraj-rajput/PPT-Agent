"""
utils/db_client.py
------------------
MongoDB connection management for the entire PPT-Agent application.

Implements a module-level singleton so the database connection is
created once and reused across all modules — no redundant connections.

Usage:
    from utils.db_client import get_collection

    raw_linkedin_collection   = get_collection("raw_linkedin")
    structured_collection     = get_collection("structured_linkedin")
    scrape_logs_collection    = get_collection("scrape_logs")
"""

from typing import Optional, Any
from motor.motor_asyncio import AsyncIOMotorClient

import pymongo
from pymongo import MongoClient
from pymongo.collection import Collection
from pymongo.database import Database

from config.settings import settings, Settings
from utils.helpers import setup_logger

logger = setup_logger(__name__)


# ---------------------------------------------------------------------------
# Singleton MongoDB Client
# ---------------------------------------------------------------------------

# These are initialized once when the first call to get_database() is made.
_mongo_client: Optional[MongoClient] = None
_mongo_database: Optional[Database] = None


def get_database() -> Database:
    """
    Returns the singleton MongoDB database instance.

    Creates the MongoClient connection on the first call, then reuses
    the same connection for every subsequent call.

    Returns:
        A pymongo Database object connected to the configured database.

    Raises:
        pymongo.errors.ConnectionFailure: If MongoDB is unreachable.
    """
    global _mongo_client, _mongo_database

    if _mongo_database is not None:
        return _mongo_database

    logger.info(f"Connecting to MongoDB at: {settings.MONGO_URI}")

    _mongo_client = MongoClient(
        settings.MONGO_URI,
        serverSelectionTimeoutMS=5000,   # Fail fast if MongoDB is not running
        connectTimeoutMS=5000,
        socketTimeoutMS=10000,
    )

    # Trigger an actual connection attempt to surface errors early
    _mongo_client.admin.command("ping")
    logger.info(f"MongoDB connected. Using database: '{settings.MONGO_DB_NAME}'")

    _mongo_database = _mongo_client[settings.MONGO_DB_NAME]
    return _mongo_database


def get_collection(collection_name: str) -> Collection:
    """
    Returns a MongoDB Collection object for the given collection name.

    Args:
        collection_name: The name of the MongoDB collection to access.
                         Collections are created automatically if they
                         do not already exist.

    Returns:
        A pymongo Collection object.

    Example:
        raw_collection = get_collection("raw_linkedin")
        raw_collection.insert_one({"company_slug": "infosys", ...})
    """
    database = get_database()
    return database[collection_name]


def close_connection() -> None:
    """
    Closes the MongoDB connection and resets the singleton.

    Should be called on application shutdown or after test teardown
    to release network resources cleanly.
    """
    global _mongo_client, _mongo_database

    if _mongo_client:
        logger.info("Closing MongoDB connection.")
        _mongo_client.close()
        _mongo_client = None
        _mongo_database = None


def ensure_indexes() -> None:
    """
    Creates all necessary MongoDB indexes for optimal query performance.

    This should be called once at application startup or during
    database migration. Safe to call multiple times (indexes are
    created only if they do not already exist).

    Indexes created:
      - raw_linkedin:        (company_slug, layer)   — find raw data by company & layer
      - structured_linkedin: (company_slug)           — unique per company
      - scrape_logs:         (company_slug, scraped_at) — audit trail queries
    """
    logger.info("Ensuring MongoDB indexes exist...")

    raw_linkedin_collection = get_collection("raw_linkedin")
    raw_linkedin_collection.create_index(
        [("company_slug", pymongo.ASCENDING), ("scrape_layer", pymongo.ASCENDING)],
        name="idx_raw_linkedin_slug_scrape_layer",
    )

    structured_linkedin_collection = get_collection("structured_linkedin")
    structured_linkedin_collection.create_index(
        [("company_slug", pymongo.ASCENDING)],
        name="idx_structured_linkedin_slug",
        unique=True,
    )

    scrape_logs_collection = get_collection("scrape_logs")
    scrape_logs_collection.create_index(
        [("company_slug", pymongo.ASCENDING), ("scraped_at", pymongo.DESCENDING)],
        name="idx_scrape_logs_slug_time",
    )

    logger.info("All MongoDB indexes are in place.")


def ensure_all_indexes() -> None:
    """
    Creates indexes for ALL collections used across all agents:
      LinkedIn agent: raw_linkedin, structured_linkedin, scrape_logs
      Website agent:  raw_website, structured_website
      Discovery:      search_cache
      Orchestrator:   company_profiles

    Safe to call repeatedly — indexes are created only if they don't already exist.
    """
    logger.info("Creating indexes for all agent collections...")

    # --- LinkedIn agent collections (already in ensure_indexes) ---
    ensure_indexes()

    # --- Website agent collections ---
    raw_website = get_collection("raw_website")
    raw_website.create_index(
        [("company_slug", pymongo.ASCENDING), ("scraped_at", pymongo.DESCENDING)],
        name="idx_raw_website_slug_time",
    )

    structured_website = get_collection("structured_website")
    structured_website.create_index(
        [("company_slug", pymongo.ASCENDING)],
        name="idx_structured_website_slug",
        unique=True,
    )

    # --- Search cache ---
    search_cache = get_collection("search_cache")
    search_cache.create_index(
        [("query", pymongo.ASCENDING)],
        name="idx_search_cache_query",
        unique=True,
    )

    # --- Unified company profiles ---
    company_profiles = get_collection("company_profiles")
    company_profiles.create_index(
        [("company_slug", pymongo.ASCENDING)],
        name="idx_company_profiles_slug",
        unique=True,
    )

    logger.info("All agent indexes are in place (7 collections).")


class MongoStorageManager:
    """Persist raw pages, cleaned pages, and final profiles into MongoDB using Motor (Async)."""

    def __init__(self, settings: Settings) -> None:
        self._client: AsyncIOMotorClient[Any] = AsyncIOMotorClient(settings.mongodb_uri)
        self._db = self._client[settings.mongodb_db_name]
        self.raw_collection = self._db[settings.raw_collection]
        self.cleaned_collection = self._db[settings.cleaned_collection]
        self.profile_collection = self._db[settings.profile_collection]
        self._indexes_ready = False

    async def ensure_indexes(self) -> None:
        if self._indexes_ready:
            return
        await self.raw_collection.create_index([("url", pymongo.ASCENDING)], unique=True, name="unique_raw_url")
        await self.cleaned_collection.create_index([("url", pymongo.ASCENDING)], unique=True, name="unique_cleaned_url")
        await self.profile_collection.create_index([("website", pymongo.ASCENDING)], unique=True, sparse=True, name="unique_profile_website")
        await self.profile_collection.create_index([("company_name", pymongo.ASCENDING)], name="profile_company_name_idx")
        self._indexes_ready = True
        logger.info("mongo_indexes_ready")

    async def upsert_raw_page(self, document: dict[str, Any]) -> str:
        await self.ensure_indexes()
        await self.raw_collection.update_one(
            {"url": document["url"]},
            {"$set": document},
            upsert=True,
        )
        stored = await self.raw_collection.find_one({"url": document["url"]}, {"_id": 1})
        return str(stored["_id"]) if stored else ""

    async def upsert_cleaned_page(self, document: dict[str, Any]) -> str:
        await self.ensure_indexes()
        await self.cleaned_collection.update_one(
            {"url": document["url"]},
            {"$set": document},
            upsert=True,
        )
        stored = await self.cleaned_collection.find_one({"url": document["url"]}, {"_id": 1})
        return str(stored["_id"]) if stored else ""

    async def upsert_company_profile(self, document: dict[str, Any]) -> str:
        await self.ensure_indexes()
        await self.profile_collection.update_one(
            {"website": document["website"]},
            {"$set": document},
            upsert=True,
        )
        stored = await self.profile_collection.find_one({"website": document["website"]}, {"_id": 1})
        return str(stored["_id"]) if stored else ""

    def close(self) -> None:
        self._client.close()
