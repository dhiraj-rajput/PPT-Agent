"""
Companies House Competitor Profiler
Generates deep UK company profiles combining officer networks, charges, PSCs, and filing history.
"""

import logging
from typing import Any

from .ch_client import CompaniesHouseClient

logger = logging.getLogger(__name__)


class CompaniesHouseCompetitorProfiler:
    def __init__(self, ch_client: CompaniesHouseClient | None = None):
        self.ch_client = ch_client or CompaniesHouseClient()

    def build_competitor_profile(self, company_number: str) -> dict[str, Any]:
        """Assembles 360-degree competitor intelligence profile for a UK entity."""
        profile = self.ch_client.get_company_profile(company_number)
        officers = self.ch_client.get_officers(company_number)
        psc = self.ch_client.get_psc(company_number)
        charges = self.ch_client.get_charges(company_number)
        insolvency = self.ch_client.get_insolvency(company_number)
        filings = self.ch_client.get_filing_history(company_number)

        # Risk scoring
        risk_signals = []
        if insolvency and insolvency.get("cases"):
            risk_signals.append("INSOLVENCY_CASE_PRESENT")
        
        if charges and charges.get("total_count", 0) > 5:
            risk_signals.append("HIGH_MORTGAGE_CHARGES")

        if profile.get("company_status") != "active":
            risk_signals.append(f"STATUS_{profile.get('company_status', '').upper()}")

        competitor_dossier = {
            "source": "Companies House",
            "company_number": profile.get("company_number"),
            "company_name": profile.get("company_name"),
            "status": profile.get("company_status"),
            "type": profile.get("company_type"),
            "incorporation_date": profile.get("date_of_creation"),
            "sic_codes": profile.get("sic_codes", []),
            "address": profile.get("registered_office_address", {}),
            "officers_count": officers.get("total_results", 0) if officers else 0,
            "officers": officers.get("items", [])[:10] if officers else [],
            "psc": psc.get("items", []) if psc else [],
            "charges_count": charges.get("total_count", 0) if charges else 0,
            "risk_signals": risk_signals,
            "recent_filings": filings.get("items", [])[:5] if filings else []
        }

        return competitor_dossier
