"""
linkedin/__init__.py
--------------------
Public API exports for the LinkedIn data collection module.

Other modules in the project (pipeline, bi_extraction, etc.) should
only import from this file — not from internal sub-modules directly.
This gives us the freedom to refactor internals without breaking callers.

Usage from other modules:
    from linkedin import scrape_company, LinkedInCompanyData, LinkedInStorage
"""

from linkedin.scraper import scrape_company
from linkedin.models import (
    LinkedInCompanyData,
    CompanyIdentity,
    CompanyDescription,
    EmployeeInsights,
    LeadershipMember,
    CompanyPost,
    JobPosting,
    CompanyLocation,
    FundingInfo,
    RawLinkedInScrapedData,
    BIProfile,
)
from linkedin.storage import LinkedInStorage
from linkedin.data_cleaner import DataCleaner
from linkedin.bi_extractor import BIExtractor

__all__ = [
    # Main entry point
    "scrape_company",

    # Data cleaners & extractors
    "DataCleaner",
    "BIExtractor",

    # Data models (for type hints in downstream modules)
    "LinkedInCompanyData",
    "CompanyIdentity",
    "CompanyDescription",
    "EmployeeInsights",
    "LeadershipMember",
    "CompanyPost",
    "JobPosting",
    "CompanyLocation",
    "FundingInfo",
    "RawLinkedInScrapedData",
    "BIProfile",

    # Storage (for pipeline to query existing data)
    "LinkedInStorage",
]
