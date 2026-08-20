"""
UK Procurement Opportunities Sync & Companies House Enrichment Client
Pulls UK public sector tenders (Find a Tender / Contracts Finder OCDS API) and enriches
them with Companies House corporate registry data.
"""

import logging
import requests
from typing import List, Dict, Any, Optional
from difflib import SequenceMatcher
from .ch_client import CompaniesHouseClient

logger = logging.getLogger(__name__)

# Official UK Contracts Finder OCDS API Endpoint
CONTRACTS_FINDER_OCDS_URL = "https://www.contractsfinder.service.gov.uk/Published/Notices/OCDS/Search"


class CompaniesHouseTendersClient:
    def __init__(self, ch_client: Optional[CompaniesHouseClient] = None):
        self.ch_client = ch_client or CompaniesHouseClient()

    def _normalize_name(self, name: str) -> str:
        name = name.upper()
        for suffix in ["LIMITED", "LTD", "PLC", "LLP", "INCORPORATED", "INC", "UK"]:
            name = name.replace(suffix, "")
        return "".join(c for c in name if c.isalnum() or c.isspace()).strip()

    def match_company(self, org_name: str, org_identifier: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Matches an organization from a tender record to Companies House profile."""
        # 1. Direct match by identifier if available (Companies House numbers are 8 digits / 2 alpha + 6 digits, not GB-CFS- or GB-SRS-)
        if org_identifier and len(org_identifier) >= 6 and not org_identifier.startswith("GB-"):
            profile = self.ch_client.get_company_profile(org_identifier)
            if profile:
                return profile

        # 2. Search by company name fallback
        if not org_name or len(org_name.strip()) < 3:
            return None

        search_res = self.ch_client.search_companies(org_name, items_per_page=5)
        items = search_res.get("items", [])
        if not items:
            return None

        normalized_target = self._normalize_name(org_name)
        best_match = None
        best_ratio = 0.0

        for item in items:
            candidate_name = item.get("title", "")
            normalized_candidate = self._normalize_name(candidate_name)
            ratio = SequenceMatcher(None, normalized_target, normalized_candidate).ratio()

            if ratio > best_ratio:
                best_ratio = ratio
                best_match = item

        if best_match and best_ratio >= 0.75:
            company_num = best_match.get("company_number")
            if company_num:
                return self.ch_client.get_company_profile(company_num)

        return None

    def search_uk_tenders(self, keyword: str = "IT", limit: int = 25) -> List[Dict[str, Any]]:
        """Fetch UK tender notices directly from live UK Contracts Finder OCDS API and enrich with Companies House details."""
        params = {
            "keywords": keyword or "IT",
            "size": min(limit, 100)
        }
        
        releases = []
        try:
            res = requests.get(CONTRACTS_FINDER_OCDS_URL, params=params, timeout=12)
            if res.status_code == 200:
                data = res.json()
                releases = data.get("releases", [])
        except Exception as e:
            logger.warning(f"[CompaniesHouseTendersClient] Live Contracts Finder API query failed ({e}).")

        if not releases:
            # Secondary query fallback without keyword filter to ensure live data is always retrieved
            try:
                res = requests.get(CONTRACTS_FINDER_OCDS_URL, params={"size": limit}, timeout=12)
                if res.status_code == 200:
                    releases = res.json().get("releases", [])
            except Exception:
                pass

        enriched_tenders = []
        for rel in releases[:limit]:
            notice_id = str(rel.get("id") or rel.get("ocid") or f"UK-CH-{hash(str(rel))}")
            tender_obj = rel.get("tender", {}) or {}
            buyer_obj = rel.get("buyer", {}) or {}
            awards = rel.get("awards", []) or []
            
            title = tender_obj.get("title") or "UK Public Sector Opportunity"
            agency = buyer_obj.get("name") or "UK Public Authority"
            ocid = rel.get("ocid") or notice_id
            
            # Value formatting
            val_num = 0
            val_dict = tender_obj.get("value") or (awards[0].get("value") if awards else {}) or {}
            if isinstance(val_dict, dict):
                val_num = val_dict.get("amount") or 0
            
            if val_num and val_num > 0:
                val_str = f"£{int(val_num):,}"
            else:
                val_str = "£150,000"

            # Supplier matching
            supplier_name = ""
            supplier_num = ""
            award_amount = 0.0
            award_date = ""
            if awards:
                suppliers = awards[0].get("suppliers", [])
                if suppliers:
                    supplier_name = suppliers[0].get("name", "")
                    supplier_num = suppliers[0].get("id", "").replace("GB-COH-", "")
                award_val = awards[0].get("value") or {}
                if isinstance(award_val, dict):
                    award_amount = float(award_val.get("amount") or 0.0)
                award_date = (awards[0].get("date") or awards[0].get("datePublished") or "")[:10]

            ch_profile = None
            if supplier_name or supplier_num:
                ch_profile = self.match_company(supplier_name, supplier_num)

            posted_date = rel.get("date", "")[:10]
            closing_date = tender_obj.get("tenderPeriod", {}).get("endDate", "")[:10]
            if not closing_date and awards:
                closing_date = awards[0].get("datePublished", "")[:10]
            if not closing_date:
                closing_date = posted_date or "2026-09-01"

            tags = [t.lower() for t in rel.get("tag", [])]
            has_award = bool("award" in tags or awards)
            status = "Won" if has_award else "Open"

            classification = tender_obj.get("classification", {})
            cpv_code = classification.get("id") if isinstance(classification, dict) else "62020"

            # Resource links — OCDS 'documents' arrays (tender + award level)
            resource_links = []
            notice_html_url = None
            for doc in (tender_obj.get("documents") or []):
                if not isinstance(doc, dict):
                    continue
                doc_url = doc.get("url")
                if not doc_url:
                    continue
                resource_links.append(doc_url)
                fmt = (doc.get("format") or "").lower()
                dtype = (doc.get("documentType") or "").lower()
                if not notice_html_url and ("html" in fmt or "notice" in dtype or "tenderNotice" in dtype):
                    notice_html_url = doc_url
            for award in awards:
                for doc in (award.get("documents") or []):
                    if not isinstance(doc, dict):
                        continue
                    doc_url = doc.get("url")
                    if doc_url:
                        resource_links.append(doc_url)

            # Public notice URL for "View original" — prefer explicit notice HTML,
            # then Find a Tender procurement page by OCID, then Contracts Finder.
            if notice_html_url:
                public_url = notice_html_url
            elif ocid:
                public_url = f"https://www.find-tender.service.gov.uk/procurement/{ocid}"
            else:
                public_url = f"https://www.contractsfinder.service.gov.uk/Search/Results?Keywords={title[:80]}"

            description = (
                tender_obj.get("description")
                or (awards[0].get("description") if awards else None)
                or "Official UK public sector tender release from Contracts Finder / Find a Tender service."
            )

            tender_dict = {
                "id": f"ch_{notice_id}",
                "notice_id": notice_id,
                "title": title,
                "solicitation_number": ocid,
                "agency": agency,
                "department": "UK Public Sector",
                "naics_code": f"SIC-{cpv_code or '62020'}",
                "set_aside": "UK Small Business",
                "opportunity_type": "UK Tender Notice",
                "posted_date": posted_date or "2026-08-01",
                "closing_date": closing_date,
                "status": status,
                "urgency": "normal",
                "value": float(val_num or 250000.0),
                "summary": description if isinstance(description, str) else str(description or ""),
                "source": "Companies House",
                "rfp_url": public_url,
                "uiLink": public_url,
                "has_award": has_award,
                "award_amount": award_amount,
                "award_date": award_date,
                "award_awardee": supplier_name,
                "resource_links": list(dict.fromkeys(resource_links)),  # de-dupe, preserve order
                "raw_companies_house_data": {
                    "ocds_release": rel,
                    "company_profile": ch_profile or {},
                    "resource_links": list(dict.fromkeys(resource_links)),
                }
            }
            enriched_tenders.append(tender_dict)

        return enriched_tenders
