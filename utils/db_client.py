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

from typing import Optional

import pymongo
from pymongo import MongoClient
from pymongo.collection import Collection
from pymongo.database import Database

from config.settings import settings
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
