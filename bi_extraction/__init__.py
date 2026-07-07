"""
bi_extraction/__init__.py
--------------------------
Business Intelligence extraction layer package.
"""

from bi_extraction.extractor import (
    HuggingFaceCompanyExtractor,
    CompanyProfile,
    ProductService,
    CompanyInsight,
    ExtractionError,
)

__all__ = [
    "HuggingFaceCompanyExtractor",
    "CompanyProfile",
    "ProductService",
    "CompanyInsight",
    "ExtractionError",
]
