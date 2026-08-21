"""
website/storage.py
------------------
MongoDB read/write operations for all website scraping data.

Collections used:
  - raw_website:        Raw HTML/text from each crawled page
  - structured_website: Final structured WebsiteData (upsert by company_slug)
  - scrape_logs:        Shared audit trail (also used by linkedin module)
"""

from datetime import datetime, timezone

from utils.db_client import get_collection
from utils.helpers import setup_logger

from pipeline.website.models import RawWebsiteScrapedData, WebsiteData

logger = setup_logger(__name__)

COLLECTION_RAW_WEBSITE = "raw_website"
COLLECTION_STRUCTURED_WEBSITE = "structured_website"
COLLECTION_SCRAPE_LOGS = "scrape_logs"


class WebsiteStorage:
    """
    Handles all MongoDB read/write operations for website scraping data.

    Usage:
        storage = WebsiteStorage()
        storage.save_raw_page(raw_page_obj)
        storage.save_website_data(website_data_obj)
        data = storage.get_website_data("infosys")
    """

    def save_raw_page(self, raw_data: RawWebsiteScrapedData) -> str:
        """Insert a raw page record into 'raw_website'. Returns the document _id."""
        collection = get_collection(COLLECTION_RAW_WEBSITE)
        document = raw_data.model_dump()
        result = collection.insert_one(document)
        doc_id = str(result.inserted_id)
        logger.info(f"Saved raw website page | slug='{raw_data.company_slug}' url='{raw_data.page_url}' id='{doc_id}'")
        return doc_id

    def save_website_data(self, data: WebsiteData) -> str:
        """
        Upsert structured website data by company_slug.
        Returns the document _id (inserted or existing).
        """
        from pymongo import ReturnDocument

        collection = get_collection(COLLECTION_STRUCTURED_WEBSITE)
        document = data.model_dump()

        updated_doc = collection.find_one_and_update(
            {"company_slug": data.company_slug},
            {"$set": document},
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )

        doc_id = str(updated_doc["_id"]) if updated_doc and "_id" in updated_doc else "unknown"
        logger.info(f"Saved website data | slug='{data.company_slug}' id='{doc_id}'")
        return doc_id

    def get_website_data(self, company_slug: str) -> WebsiteData | None:
        """Retrieve structured website data for a company_slug. Returns None if not found."""
        collection = get_collection(COLLECTION_STRUCTURED_WEBSITE)
        document = collection.find_one({"company_slug": company_slug})
        if document is None:
            return None
        document.pop("_id", None)
        return WebsiteData(**document)

    def website_data_exists(self, company_slug: str) -> bool:
        """Return True if structured website data exists for this company_slug."""
        collection = get_collection(COLLECTION_STRUCTURED_WEBSITE)
        return collection.count_documents({"company_slug": company_slug}, limit=1) > 0

    def log_scrape_operation(
        self,
        company_slug: str,
        source: str,
        scrape_status: str,
        duration_seconds: float,
        error_message: str | None = None,
    ) -> None:
        """Append an audit log entry to the shared 'scrape_logs' collection."""
        collection = get_collection(COLLECTION_SCRAPE_LOGS)
        log_entry = {
            "company_slug": company_slug,
            "agent_name": "website",
            "source": source,
            "status": scrape_status,
            "scrape_status": scrape_status,
            "duration_seconds": round(duration_seconds, 2),
            "error_message": error_message,
            "timestamp": datetime.now(tz=timezone.utc),
            "scraped_at": datetime.now(tz=timezone.utc),
        }
        collection.insert_one(log_entry)
        logger.info(
            f"Scrape log [{source}] | slug='{company_slug}' "
            f"status='{scrape_status}' duration={duration_seconds:.2f}s"
        )
