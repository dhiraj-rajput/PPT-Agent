"""
tests/unit/test_normalizer.py
------------------------------
Unit tests for models/normalizer.py to verify data cleaning,
garbage filtering, phone validation, and pre-merge normalisation logic.
"""

import pytest
from pipeline.models.normalizer import (
    normalize_company_intelligence,
    _is_valid_phone,
    _is_nav_garbage,
    clean_list,
    merge_lists,
)


def test_is_valid_phone():
    # Valid phone formats
    assert _is_valid_phone("+91 (80) 28440254") is True
    assert _is_valid_phone("+1-800-555-0100") is True
    assert _is_valid_phone("0120-123-456") is True
    assert _is_valid_phone("+44 20 7946 0958") is True

    # Year ranges (must be rejected)
    assert _is_valid_phone("2021-2022") is False
    assert _is_valid_phone("2021-2025") is False
    assert _is_valid_phone("1999/2000") is False

    # Too short / non-phone
    assert _is_valid_phone("2024") is False
    assert _is_valid_phone("12345") is False
    assert _is_valid_phone("hello world") is False


def test_is_nav_garbage():
    # True for UI / cookie / terms patterns
    assert _is_nav_garbage("Privacy Preference Centre") is True
    assert _is_nav_garbage("cookie policy") is True
    assert _is_nav_garbage("all rights reserved") is True
    assert _is_nav_garbage("please fill required field") is True
    assert _is_nav_garbage("strictly necessary cookies") is True
    assert _is_nav_garbage("always active") is True
    assert _is_nav_garbage("functional cookies") is True
    assert _is_nav_garbage("log in") is True
    assert _is_nav_garbage("sign up") is True
    assert _is_nav_garbage("submit") is True
    assert _is_nav_garbage("undefined") is True
    assert _is_nav_garbage("and launching new products") is True
    assert _is_nav_garbage("and launching the platform") is True
    assert _is_nav_garbage("models faster than competitors") is True
    assert _is_nav_garbage("please select from drop down") is True
    assert _is_nav_garbage("for more information click here") is True

    # False for real content
    assert _is_nav_garbage("Wipro Intelligence Platform") is False
    assert _is_nav_garbage("Cloud Migration Services") is False
    assert _is_nav_garbage("Apala Mallick") is False


def test_clean_list():
    raw_list = [
        "Wipro Platform",
        "",
        None,
        "   ",
        "Privacy Preference Centre",
        "Always Active",
        "Cloud Services",
        "Wipro Platform",  # duplicate (case-insensitive)
        "wipro platform",  # duplicate (case-insensitive)
        "A very long sentence " * 20,  # too long
    ]
    cleaned = clean_list(raw_list, max_len=100)
    assert cleaned == ["Wipro Platform", "Cloud Services"]


def test_merge_lists():
    list1 = ["Product A", "Product B"]
    list2 = ["Product B", "Product C", "Privacy Policy"]
    merged = merge_lists(list1, list2)
    assert merged == ["Product A", "Product B", "Product C"]


def test_normalize_company_intelligence():
    website_data = {
        "company_name": "TestCorp",
        "website_url": "https://testcorp.com",
        "industry": "Tech",
        "description": "TestCorp is a leading software provider.",
        "headquarters": "New York, USA",
        "locations": ["New York", "London"],
        "products": ["Product A", "Privacy Preference Centre"],
        "services": ["Service A", "Always Active"],
        "emails": ["contact@testcorp.com"],
        "phone_numbers": ["+1-800-555-0100", "2021-2022"],
        "social_links": ["https://linkedin.com/company/testcorp"],
        "clean_text": "Sample website text body here.",
    }

    linkedin_data = {
        "identity": {
            "company_name": "TestCorp Ltd",
            "industry": "IT Services",
            "headquarters_location": "New York City, USA",
            "company_size_range": "500-1000 employees",
            "founded_year": 2010,
            "tagline": "Innovating the future",
            "website_url": "https://www.testcorp.com",
        },
        "description": {
            "about_text": "TestCorp is a global consulting firm.",
            "mission_statement": "To deliver value.",
        },
        "bi_profile": {
            "products_and_services": [
                {"name": "Product B", "description": "Cloud storage solutions"},
            ],
            "tech_stack": {
                "frameworks_and_tools": ["React", "Kubernetes"],
                "languages": ["Python"],
            },
            "key_differentiators": ["Global reach", "Expert team"],
        },
        "leadership_team": [
            {"full_name": "Jane Doe", "title": "CEO"},
        ],
    }

    external_insights = {
        "business_model": "SaaS and consulting services.",
        "value_proposition": "Custom solutions with cloud expertise.",
        "products_and_services": [
            {"name": "Product C", "description": "Managed cloud services"},
        ],
        "insights": [
            {
                "category": "Competitor Analysis",
                "description": "Main competitors are RivalCorp and BizCorp.",
                "source_url": "https://rivals.com",
                "confidence_score": 0.95,
            },
            {
                "category": "Financial Performance",
                "description": "Revenue reached $50M in 2025, up 15% YoY.",
                "source_url": "https://financials.com",
                "confidence_score": 0.9,
            },
        ],
    }

    google_data = {
        "results": [
            {"title": "TestCorp Q4 earnings report", "url": "https://news.com/q4", "snippet": "TestCorp announces record growth"},
        ]
    }

    normalized = normalize_company_intelligence(
        website_data=website_data,
        linkedin_data=linkedin_data,
        google_data=google_data,
        external_insights=external_insights,
    )

    # Asserts
    assert normalized["company_name"] == "TestCorp Ltd"
    assert normalized["website"] == "https://testcorp.com"
    assert normalized["founded_year"] == 2010
    assert normalized["employee_count"] == "500-1000 employees"
    assert normalized["tagline"] == "Innovating the future"
    
    # Locations
    assert "New York, USA" in normalized["locations"]
    assert "New York City, USA" in normalized["locations"]
    
    # Products & Services (garbage filtered)
    assert "Product A" in normalized["products"]
    assert "Product B" in normalized["products"]
    assert "Product C" in normalized["products"]
    assert "Privacy Preference Centre" not in normalized["products"]
    assert "Service A" in normalized["services"]
    assert "Always Active" not in normalized["services"]
    
    # Tech Stack
    assert "React" in normalized["technology_stack"]
    assert "Python" in normalized["technology_stack"]
    
    # Competitors and Financials
    assert "Main competitors are RivalCorp and BizCorp." in normalized["competitors"]
    assert "Revenue reached $50M in 2025, up 15% YoY." in normalized["financial_highlights"]
    
    # Phones (garbage years filtered)
    assert "+1-800-555-0100" in normalized["phone_numbers"]
    assert "2021-2022" not in normalized["phone_numbers"]
