"""
tests/unit/test_compactor.py
----------------------------
Unit tests for models/compactor.py, verifying URL helpers,
rule-based compaction logic, and end-to-end compaction wrapper.
"""

import pytest
from pipeline.models.compactor import (
    BusinessIntelligenceCompactor,
    _canonical_website,
    _domain_key,
)


def test_url_helpers():
    assert _canonical_website("wipro.com") == "https://wipro.com/"
    assert _canonical_website("http://WIPRO.COM/about") == "http://wipro.com/about"
    assert _canonical_website("") == ""

    assert _domain_key("https://www.wipro.com/index.html") == "wipro_com"
    assert _domain_key("http://wipro-tech.co.uk/") == "wipro_tech_co_uk"
    assert _domain_key("") == ""


def test_rules_compaction():
    compactor = BusinessIntelligenceCompactor()
    
    # Normalized dictionary containing mock scrapings
    normalized = {
        "company_name": "TestCorp",
        "website": "https://testcorp.com",
        "industry": "Information Technology",
        "headquarters": "San Francisco, CA",
        "specialties": ["Cloud Computing", "AI Integration"],
        "descriptions": {
            "linkedin": "TestCorp is a leading SaaS provider offering advanced cloud solutions.",
            "website": "Welcome to TestCorp, your premier AI partner."
        },
        "technology_stack": ["AWS", "Python", "Snowflake"],
        "business_model": "",
        "financial_highlights": [],
        "competitors": [],
        "value_proposition": "",
        "key_differentiators": ["High security SLA", "Experienced engineering team"],
        "competitive_advantages": ["Patented AI algorithms"]
    }
    
    profile = compactor._run_rules_compaction(normalized)
    
    assert profile["company_name"] == "TestCorp"
    assert profile["website"] == "https://testcorp.com"
    assert "SaaS" in profile["business_model"]
    assert "Subscription-based pricing" in profile["pricing_model"]
    assert len(profile["rfp_strengths"]) >= 3
    assert "AWS" in profile["technology_stack"]
