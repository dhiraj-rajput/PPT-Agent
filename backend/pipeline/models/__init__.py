"""
models/
-------
Shared Pydantic models and data transformation utilities for the PPT-Agent pipeline.

Modules:
    company_schema  — Pydantic models for raw agent outputs and the final OptimizedCompanyProfile
    normalizer      — Merges/normalises outputs from all three agents into a single dict
    compactor       — Rule-based compactor that produces the final OptimizedCompanyProfile
"""

from pipeline.models.compactor import BusinessIntelligenceCompactor
from pipeline.models.company_schema import (
    CompanyIntelligence,
    CompanyMongoRecord,
    CrawlMetadata,
    OptimizedCompanyProfile,
)
from pipeline.models.normalizer import normalize_company_intelligence

__all__ = [
    "BusinessIntelligenceCompactor",
    "CompanyIntelligence",
    "CompanyMongoRecord",
    "CrawlMetadata",
    "OptimizedCompanyProfile",
    "normalize_company_intelligence",
]
