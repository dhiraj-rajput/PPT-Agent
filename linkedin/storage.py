"""
linkedin/storage.py
-------------------
MongoDB read and write operations for all LinkedIn data.

This module is the only place in the codebase that directly touches
MongoDB for LinkedIn data. All other modules interact with storage
through these functions — keeping data access logic centralized.

Collections used:
  - raw_linkedin:        Raw HTML/text from each scraping layer
  - structured_linkedin: Final structured LinkedInCompanyData objects
  - scrape_logs:         Audit trail of all scraping operations
"""

from datetime import datetime
from typing import Optional

from bson import ObjectId
from pymongo import DESCENDING

from linkedin.constants import (
    COLLECTION_RAW_LINKEDIN,
    COLLECTION_SCRAPE_LOGS,
    COLLECTION_STRUCTURED_LINKEDIN,
)
from linkedin.models import LinkedInCompanyData, RawLinkedInScrapedData
from utils.db_client import get_collection
from utils.helpers import get_utc_now, setup_logger

logger = setup_logger(__name__)


class LinkedInStorage:
    """
    Handles all MongoDB read and write operations for LinkedIn data.

    Usage:
        storage = LinkedInStorage()

        # Save raw scraped HTML from Layer 1
        raw_id = storage.save_raw_scraped_data(raw_data_object)

        # Save the final structured company data
        storage.save_structured_company_data(company_data_object)

        # Retrieve structured data for a company
        data = storage.get_structured_company_data("infosys")

        # Check if we have fresh data already
        if storage.company_data_exists("infosys"):
            ...
    """

    def save_raw_scraped_data(self, raw_data: RawLinkedInScrapedData) -> str:
        """
        Saves raw scraped data (HTML, text, JSON-LD) from a single scraping layer.

        Each call inserts a new document — we keep all raw data from all
        layers and all scrape runs for auditing and re-processing.

        Args:
            raw_data: A RawLinkedInScrapedData object containing the scraped content.

        Returns:
            The MongoDB ObjectId (as a string) of the inserted document.
        """
        collection = get_collection(COLLECTION_RAW_LINKEDIN)

        document = raw_data.model_dump()

        result = collection.insert_one(document)
        inserted_id = str(result.inserted_id)

        logger.info(
            f"Saved raw data | company='{raw_data.company_slug}' "
            f"layer='{raw_data.scrape_layer}' | doc_id='{inserted_id}'"
        )
        return inserted_id

    def save_structured_company_data(
        self,
        company_data: LinkedInCompanyData,
    ) -> str:
        """
        Saves the final structured LinkedIn company data to MongoDB.

        Uses upsert (insert or replace) — so re-scraping a company
        always updates the existing document rather than creating duplicates.
        The unique key is `company_slug`.

        Args:
            company_data: A fully populated LinkedInCompanyData object.

        Returns:
            The MongoDB ObjectId (as a string) of the upserted document.
        """
        collection = get_collection(COLLECTION_STRUCTURED_LINKEDIN)

        document = company_data.model_dump()

        # Upsert: update if company_slug exists, insert if not
        result = collection.update_one(
            filter={"company_slug": company_data.company_slug},
            update={"$set": document},
            upsert=True,
        )

        # Get the ID: either the newly inserted document or the existing one
        if result.upserted_id:
            document_id = str(result.upserted_id)
            logger.info(
                f"Inserted structured data | company='{company_data.company_slug}' "
                f"| doc_id='{document_id}'"
            )
        else:
            existing_document = collection.find_one(
                {"company_slug": company_data.company_slug},
                {"_id": 1},
            )
            document_id = str(existing_document["_id"]) if existing_document else "unknown"
            logger.info(
                f"Updated structured data | company='{company_data.company_slug}' "
                f"| doc_id='{document_id}'"
            )

        return document_id

    def get_structured_company_data(
        self,
        company_slug: str,
    ) -> Optional[LinkedInCompanyData]:
        """
        Retrieves the latest structured company data for a given slug.

        Args:
            company_slug: The LinkedIn URL slug, e.g. 'infosys'.

        Returns:
            A LinkedInCompanyData object if found, otherwise None.
        """
        collection = get_collection(COLLECTION_STRUCTURED_LINKEDIN)

        document = collection.find_one({"company_slug": company_slug})

        if document is None:
            logger.debug(f"No structured data found for company='{company_slug}'")
            return None

        # Remove MongoDB's internal _id field before parsing into Pydantic
        document.pop("_id", None)

        logger.debug(f"Retrieved structured data for company='{company_slug}'")
        return LinkedInCompanyData(**document)

    def company_data_exists(self, company_slug: str) -> bool:
        """
        Checks whether structured data already exists for a given company.

        Useful for caching — skip scraping if we have recent data.

        Args:
            company_slug: The LinkedIn URL slug, e.g. 'google'.

        Returns:
            True if a document exists in structured_linkedin, False otherwise.
        """
        collection = get_collection(COLLECTION_STRUCTURED_LINKEDIN)

        count = collection.count_documents(
            {"company_slug": company_slug},
            limit=1,
        )
        return count > 0

    def log_scrape_operation(
        self,
        company_slug: str,
        scrape_status: str,
        layers_used: list[str],
        duration_seconds: float,
        error_message: Optional[str] = None,
    ) -> None:
        """
        Records an audit log entry for a scraping operation.

        Logs are stored in the 'scrape_logs' collection and can be
        used to track success rates, debug failures, and monitor
        scraping performance over time.

        Args:
            company_slug:      LinkedIn slug of the company that was scraped.
            scrape_status:     "success", "partial", or "failed".
            layers_used:       List of layers that ran, e.g. ["public", "crawl4ai"].
            duration_seconds:  How long the full scrape took in seconds.
            error_message:     Error description if status is "failed" or "partial".
        """
        collection = get_collection(COLLECTION_SCRAPE_LOGS)

        log_entry = {
            "company_slug": company_slug,
            "agent_name": "linkedin",
            "status": scrape_status,
            "scrape_status": scrape_status,
            "layers_used": layers_used,
            "duration_seconds": round(duration_seconds, 2),
            "error_message": error_message,
            "timestamp": get_utc_now(),
            "scraped_at": get_utc_now(),
            "details": {"layers_used": layers_used}
        }

        collection.insert_one(log_entry)

        logger.info(
            f"Scrape log | company='{company_slug}' "
            f"status='{scrape_status}' "
            f"layers={layers_used} "
            f"duration={duration_seconds:.2f}s"
        )

    def get_recent_scrape_logs(
        self,
        company_slug: str,
        limit: int = 10,
    ) -> list[dict]:
        """
        Retrieves the most recent scrape log entries for a company.

        Args:
            company_slug: The LinkedIn URL slug.
            limit:        Maximum number of log entries to return.

        Returns:
            A list of log entry dicts, newest first.
        """
        collection = get_collection(COLLECTION_SCRAPE_LOGS)

        logs = list(
            collection.find(
                {"company_slug": company_slug},
                {"_id": 0},
            )
            .sort("scraped_at", DESCENDING)
            .limit(limit)
        )

        return logs
