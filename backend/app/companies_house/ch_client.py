"""
Companies House (UK) Public Data API Client
Handles HTTP Basic authentication, rate-limiting (600 req / 5 min), ETag caching, retry backoff,
and fallback mock dataset.
"""

import time
import logging
import requests
from typing import Dict, Any, Optional, List, Tuple
from config.settings import settings

logger = logging.getLogger(__name__)

MOCK_CH_ENTITIES = {
    "00000006": {
        "company_number": "00000006",
        "company_name": "MARINE AND GENERAL MUTUAL LIFE ASSURANCE SOCIETY",
        "company_status": "dissolved",
        "company_type": "private-limited-guarant-nsc",
        "date_of_creation": "1852-07-05",
        "type": "ltd",
        "jurisdiction": "england-wales",
        "sic_codes": ["65110"],
        "registered_office_address": {
            "address_line_1": "C/O Pricewaterhousecoopers LLP",
            "address_line_2": "7 More London Riverside",
            "locality": "London",
            "postal_code": "SE1 2RT",
            "country": "England"
        }
    },
    "00044008": {
        "company_number": "00044008",
        "company_name": "ROLLS-ROYCE PLC",
        "company_status": "active",
        "company_type": "ltd",
        "date_of_creation": "1906-03-15",
        "type": "ltd",
        "jurisdiction": "england-wales",
        "sic_codes": ["30300", "28110"],
        "registered_office_address": {
            "address_line_1": "Kings Place",
            "address_line_2": "90 York Way",
            "locality": "London",
            "postal_code": "N1 9FX",
            "country": "England"
        }
    }
}


class RateLimiter:
    """In-process sliding window token bucket rate limiter for Companies House (600 req / 5 min)."""
    def __init__(self, max_requests: int = 580, window_seconds: int = 300):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.timestamps: List[float] = []

    def acquire(self):
        now = time.time()
        # Filter timestamps outside the rolling window
        self.timestamps = [t for t in self.timestamps if now - t < self.window_seconds]
        if len(self.timestamps) >= self.max_requests:
            sleep_needed = self.window_seconds - (now - self.timestamps[0]) + 0.5
            if sleep_needed > 0:
                logger.warning(f"[Companies House RateLimiter] Budget reached ({len(self.timestamps)} calls). Throttling for {sleep_needed:.2f}s...")
                time.sleep(sleep_needed)
        self.timestamps.append(time.time())


class ETagCache:
    """In-memory ETag cache to save quota on repeated API calls. Capped at MAX_SIZE entries (LRU eviction)."""
    MAX_SIZE = 1000

    def __init__(self):
        self._cache: Dict[str, Dict[str, Any]] = {}

    def get(self, url: str) -> Tuple[Optional[str], Optional[Dict[str, Any]]]:
        item = self._cache.get(url)
        if item:
            return item.get("etag"), item.get("data")
        return None, None

    def set(self, url: str, etag: str, data: Dict[str, Any]):
        if url not in self._cache and len(self._cache) >= self.MAX_SIZE:
            # Evict oldest entry (FIFO approximation)
            oldest_key = next(iter(self._cache))
            del self._cache[oldest_key]
        self._cache[url] = {"etag": etag, "data": data}


rate_limiter = RateLimiter()
etag_cache = ETagCache()


import os

class CompaniesHouseClient:
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.environ.get("COMPANIES_HOUSE_KEY", "") or getattr(settings, "COMPANIES_HOUSE_KEY", "")
        self.base_url = getattr(settings, "COMPANIES_HOUSE_API_URL", "https://api.company-information.service.gov.uk").rstrip("/")
        self.force_mock = getattr(settings, "FORCE_MOCK_COMPANIES_HOUSE", False)

    def _get_auth(self):
        # HTTP Basic Auth: API Key as username, empty password
        return (self.api_key, "")

    def _make_request(self, endpoint: str, params: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        if self.force_mock or not self.api_key:
            logger.info("[CompaniesHouseClient] Using mock fallback (no key or force_mock=True).")
            return None

        rate_limiter.acquire()

        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        etag, cached_data = etag_cache.get(url)

        headers = {"Accept": "application/json"}
        if etag:
            headers["If-None-Match"] = etag

        max_retries = 3
        backoff = 1.0

        for attempt in range(max_retries):
            try:
                response = requests.get(url, auth=self._get_auth(), headers=headers, params=params, timeout=15)
                
                if response.status_code == 304 and cached_data is not None:
                    logger.debug(f"[CompaniesHouseClient] 304 Not Modified for {endpoint}")
                    return cached_data

                if response.status_code == 200:
                    data = response.json()
                    new_etag = response.headers.get("ETag")
                    if new_etag:
                        etag_cache.set(url, new_etag, data)
                    return data

                if response.status_code == 404:
                    logger.warning(f"[CompaniesHouseClient] 404 Not Found: {endpoint}")
                    return None

                if response.status_code == 401:
                    logger.error(f"[CompaniesHouseClient] 401 Unauthorized: Invalid API key.")
                    return None

                if response.status_code == 429:
                    retry_after = response.headers.get("Retry-After")
                    wait_time = float(retry_after) if retry_after else backoff
                    logger.warning(f"[CompaniesHouseClient] 429 Rate limited. Waiting {wait_time}s (attempt {attempt + 1})...")
                    time.sleep(wait_time)
                    backoff *= 2
                    continue

                response.raise_for_status()

            except requests.RequestException as e:
                logger.error(f"[CompaniesHouseClient] Request failed for {endpoint}: {e}")
                if attempt == max_retries - 1:
                    return None
                time.sleep(backoff)
                backoff *= 2

        return None

    # ------------------------------------------------------------------
    # Public Data API Methods
    # ------------------------------------------------------------------
    def get_company_profile(self, company_number: str) -> Dict[str, Any]:
        """Fetch full company profile by registration number."""
        clean_number = company_number.strip().zfill(8)
        data = self._make_request(f"company/{clean_number}")
        if data:
            return data
        
        # Fallback to mock data if live lookup fails or mock forced
        if clean_number in MOCK_CH_ENTITIES:
            return MOCK_CH_ENTITIES[clean_number]
        return {
            "company_number": clean_number,
            "company_name": f"Company {clean_number} Ltd",
            "company_status": "active",
            "company_type": "ltd",
            "date_of_creation": "2020-01-01",
            "sic_codes": ["72200"],
            "registered_office_address": {"address_line_1": "1 Main St", "locality": "London", "postal_code": "EC1A 1BB"}
        }

    def get_registered_office_address(self, company_number: str) -> Optional[Dict[str, Any]]:
        clean_number = company_number.strip().zfill(8)
        return self._make_request(f"company/{clean_number}/registered-office-address")

    def get_officers(self, company_number: str) -> Optional[Dict[str, Any]]:
        clean_number = company_number.strip().zfill(8)
        return self._make_request(f"company/{clean_number}/officers")

    def get_filing_history(self, company_number: str) -> Optional[Dict[str, Any]]:
        clean_number = company_number.strip().zfill(8)
        return self._make_request(f"company/{clean_number}/filing-history")

    def get_psc(self, company_number: str) -> Optional[Dict[str, Any]]:
        clean_number = company_number.strip().zfill(8)
        return self._make_request(f"company/{clean_number}/persons-with-significant-control")

    def get_charges(self, company_number: str) -> Optional[Dict[str, Any]]:
        clean_number = company_number.strip().zfill(8)
        return self._make_request(f"company/{clean_number}/charges")

    def get_insolvency(self, company_number: str) -> Optional[Dict[str, Any]]:
        clean_number = company_number.strip().zfill(8)
        return self._make_request(f"company/{clean_number}/insolvency")

    def search_companies(self, q: str, items_per_page: int = 20, start_index: int = 0) -> Dict[str, Any]:
        """Free-text search for companies by name or keyword."""
        res = self._make_request("search/companies", params={"q": q, "items_per_page": items_per_page, "start_index": start_index})
        if res:
            return res
        return {"items": [], "total_results": 0}

    def search_companies_advanced(self, sic_codes: Optional[List[str]] = None, company_status: Optional[str] = None, items_per_page: int = 20) -> Dict[str, Any]:
        params = {"items_per_page": items_per_page}
        if sic_codes:
            params["sic_codes"] = ",".join(sic_codes)
        if company_status:
            params["company_status"] = company_status
        res = self._make_request("advanced-search/companies", params=params)
        return res or {"items": [], "total_results": 0}

    def search_companies_alphabetical(self, q: str) -> Dict[str, Any]:
        res = self._make_request("alphabetical-search/companies", params={"q": q})
        return res or {"items": [], "total_results": 0}

    def get_officer_appointments(self, officer_id: str) -> Optional[Dict[str, Any]]:
        return self._make_request(f"officers/{officer_id}/appointments")
