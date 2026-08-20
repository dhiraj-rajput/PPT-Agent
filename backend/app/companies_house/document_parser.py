"""
Companies House Document API Parser & Content Extractor
Downloads filing documents (PDF/images) via the Document API endpoint:
https://document-api.company-information.service.gov.uk/document/{document_id}/content
"""

import os
import logging
import requests
from typing import Optional, Dict, Any
from config.settings import settings
from .ch_client import CompaniesHouseClient

logger = logging.getLogger(__name__)


class CompaniesHouseDocumentParser:
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.environ.get("COMPANIES_HOUSE_KEY", "") or getattr(settings, "COMPANIES_HOUSE_KEY", "")
        self.doc_base_url = getattr(settings, "COMPANIES_HOUSE_DOCUMENT_API_URL", "https://document-api.company-information.service.gov.uk").rstrip("/")
        self.ch_client = CompaniesHouseClient(api_key=self.api_key)

    def get_document_metadata(self, document_id: str) -> Optional[Dict[str, Any]]:
        """Fetch metadata for a document (content_type, created_at, size)."""
        url = f"{self.doc_base_url}/document/{document_id}"
        try:
            res = requests.get(url, auth=(self.api_key, ""), timeout=15)
            if res.status_code == 200:
                return res.json()
        except Exception as e:
            logger.error(f"[DocumentParser] Metadata error for doc {document_id}: {e}")
        return None

    def download_document_content(self, document_id: str, output_dir: str) -> Optional[str]:
        """
        Downloads document binary (PDF/image) and saves to disk, following redirects.
        Returns the local file path on success, or None on failure — callers must
        check for None. This previously fell back to writing a fake placeholder
        PDF on ANY failure (auth error, network error, 404, etc.) and returned
        that path as if it had succeeded, so a real download failure was
        indistinguishable from success and the caller silently displayed/served
        garbage content instead of the real filing.
        """
        if not self.api_key:
            logger.error("[DocumentParser] No Companies House API key configured — cannot download document.")
            return None

        url = f"{self.doc_base_url}/document/{document_id}/content"
        headers = {"Accept": "application/pdf, application/json, */*"}

        os.makedirs(output_dir, exist_ok=True)
        file_path = os.path.join(output_dir, f"{document_id}.pdf")

        max_retries = 3
        backoff = 1.0
        for attempt in range(max_retries):
            try:
                res = requests.get(url, auth=(self.api_key, ""), headers=headers, allow_redirects=True, timeout=30)
                if res.status_code == 200 and res.content:
                    with open(file_path, "wb") as f:
                        f.write(res.content)
                    logger.info(f"[DocumentParser] Successfully downloaded filing doc {document_id} to {file_path}")
                    return file_path
                if res.status_code in (401, 403):
                    logger.error(f"[DocumentParser] Auth error {res.status_code} downloading doc {document_id}. Check COMPANIES_HOUSE_KEY.")
                    return None
                if res.status_code == 404:
                    logger.warning(f"[DocumentParser] Document {document_id} not found (404).")
                    return None
                if res.status_code == 429:
                    import time
                    retry_after = res.headers.get("Retry-After")
                    wait_time = float(retry_after) if retry_after else backoff
                    logger.warning(f"[DocumentParser] 429 rate limited on doc {document_id}. Waiting {wait_time}s.")
                    time.sleep(wait_time)
                    backoff *= 2
                    continue
                logger.warning(f"[DocumentParser] Unexpected status {res.status_code} downloading doc {document_id}.")
            except Exception as e:
                logger.error(f"[DocumentParser] Content download error for doc {document_id} (attempt {attempt + 1}): {e}")
                if attempt < max_retries - 1:
                    import time
                    time.sleep(backoff)
                    backoff *= 2

        logger.error(f"[DocumentParser] Failed to download document {document_id} after {max_retries} attempts.")
        return None
