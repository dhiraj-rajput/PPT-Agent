"""
models/
-------
Shared Pydantic models and data transformation utilities for the PPT-Agent pipeline.

Modules:
    company_schema  — Pydantic models for raw agent outputs and the final OptimizedCompanyProfile
    normalizer      — Merges/normalises outputs from all three agents into a single dict
    compactor       — Rule-based compactor that produces the final OptimizedCompanyProfile
"""

from models.company_schema import (
    CompanyIntelligence,
    CrawlMetadata,
    CompanyMongoRecord,
    OptimizedCompanyProfile,
)
from models.normalizer import normalize_company_intelligence
from models.compactor import BusinessIntelligenceCompactor

__all__ = [
    "CompanyIntelligence",
    "CrawlMetadata",
    "CompanyMongoRecord",
    "OptimizedCompanyProfile",
    "normalize_company_intelligence",
    "BusinessIntelligenceCompactor",
]
