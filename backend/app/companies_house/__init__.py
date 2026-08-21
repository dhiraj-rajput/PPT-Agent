"""
Companies House (UK) Integration Package
Provides API clients, opportunity search/enrichment, document parsing, and competitor profilers.
"""

from .ch_client import CompaniesHouseClient
from .competitor_profiler import CompaniesHouseCompetitorProfiler
from .document_parser import CompaniesHouseDocumentParser
from .opportunities import CompaniesHouseTendersClient

__all__ = [
    "CompaniesHouseClient",
    "CompaniesHouseCompetitorProfiler",
    "CompaniesHouseDocumentParser",
    "CompaniesHouseTendersClient",
]
