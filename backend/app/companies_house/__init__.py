"""
Companies House (UK) Integration Package
Provides API clients, opportunity search/enrichment, document parsing, and competitor profilers.
"""

from .ch_client import CompaniesHouseClient
from .opportunities import CompaniesHouseTendersClient
from .document_parser import CompaniesHouseDocumentParser
from .competitor_profiler import CompaniesHouseCompetitorProfiler

__all__ = [
    "CompaniesHouseClient",
    "CompaniesHouseTendersClient",
    "CompaniesHouseDocumentParser",
    "CompaniesHouseCompetitorProfiler",
]
