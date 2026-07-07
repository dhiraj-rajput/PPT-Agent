"""
google_search/__init__.py
--------------------------
Public API for the company discovery module.

Finds a company's official website and LinkedIn URL from any input
(company name, website URL, etc.) using Tavily search.

Usage:
    from google_search import CompanyDiscovery
    discovery = CompanyDiscovery()
    result = discovery.find_all("Infosys")
    # result = {"website_url": "https://infosys.com", "linkedin_url": "https://linkedin.com/company/infosys"}
"""

from google_search.search_client import CompanyDiscovery

__all__ = ["CompanyDiscovery"]
