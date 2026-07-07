"""
tests/unit/test_orchestrator_and_website.py
-------------------------------------------
Unit tests for Google Search discovery, Website agent components,
and the LangGraph orchestrator routing logic.
"""

import pytest
from google_search.search_client import CompanyDiscovery
from website.classifier import classify_text_by_sections
from website.extractor import extract_company_intelligence, identify_role_pages
from website.models import WebsiteData
from website.urls import normalize_url, is_internal_link, should_ignore_url, get_url_priority
from orchestrator.nodes import classify_input
from orchestrator.graph import build_graph


# ===========================================================================
# 1. Google Search / Discovery Tests
# ===========================================================================

def test_company_discovery_heuristics():
    discovery = CompanyDiscovery()
    
    # Test LinkedIn URL detection
    assert discovery._is_linkedin_url("https://www.linkedin.com/company/infosys") is True
    assert discovery._is_linkedin_url("https://infosys.com") is False
    
    # Test LinkedIn URL normalization
    assert discovery._normalize_linkedin_url("https://www.linkedin.com/company/infosys/") == "https://www.linkedin.com/company/infosys"
    assert discovery._normalize_linkedin_url("https://www.linkedin.com/company/infosys?utm_source=ref") == "https://www.linkedin.com/company/infosys"

    # Test extract name from LinkedIn URL
    assert discovery._extract_name_from_linkedin_url("https://www.linkedin.com/company/infosys-technologies") == "Infosys Technologies"
    assert discovery._extract_name_from_linkedin_url("https://www.linkedin.com/company/google") == "Google"


# ===========================================================================
# 2. Website URL utility Tests
# ===========================================================================

def test_website_url_helpers():
    # Test domain matches
    assert is_internal_link("https://www.infosys.com/about.html", "https://infosys.com") is True
    assert is_internal_link("https://google.com", "https://infosys.com") is False

    # Test URL normalization
    assert normalize_url("/about/", "https://infosys.com") == "https://infosys.com/about"
    assert normalize_url("https://infosys.com/jobs?utm_medium=cpc", "https://infosys.com") == "https://infosys.com/jobs"

    # Test ignore list
    assert should_ignore_url("https://infosys.com/privacy-policy") is True
    assert should_ignore_url("https://infosys.com/terms") is True
    assert should_ignore_url("https://infosys.com/logo.png") is True
    assert should_ignore_url("https://infosys.com/careers") is False

    # Test priority scoring
    assert get_url_priority("https://infosys.com/") == 10
    assert get_url_priority("https://infosys.com/about-us") == 5
    assert get_url_priority("https://infosys.com/some-random-subpage") == 1


# ===========================================================================
# 3. Website Classifier & Extractor Tests
# ===========================================================================

def test_website_classifier():
    sample_text = """
    About Us
    Infosys is a global leader in next-generation digital services and consulting.
    We enable clients in 50 countries to navigate their digital transformation.
    
    Products
    We offer Infosys Finacle, a industry leading digital banking solution.
    Infosys Cobalt is our cloud services suite.
    
    Leadership Team
    Salil Parekh is the Chief Executive Officer and Managing Director.
    """
    
    sections = classify_text_by_sections(sample_text)
    
    assert len(sections["Company Overview"]) > 0
    assert len(sections["Products"]) > 0
    assert len(sections["Leadership"]) > 0
    
    # Check that services text is found in Company Overview or Services
    joined_overview = " ".join(sections["Company Overview"] + sections["Services"]).lower()
    assert "digital services" in joined_overview


def test_website_intelligence_extractor():
    page_metadata = {
        "https://infosys.com": {
            "title": "Infosys - Digital Services & Consulting | Infosys",
            "description": "Infosys is a global leader in next-generation digital services."
        }
    }
    
    classified = {
        "Company Overview": ["Infosys is a leading global consulting and IT services firm."],
        "Products": ["Finacle banking platform", "Cobalt Cloud suite"],
        "Services": ["Cloud consulting", "Application management"],
        "Locations": ["Headquartered in Bangalore, India."],
        "Contact": ["Call us at +91 80 2852 0261"],
        "Leadership": ["CEO Salil Parekh leads the team."],
        "Clients": ["We work with large enterprises like BP and Daimler."],
        "Partners": ["Microsoft is a key alliance partner."],
        "Industries": ["Serving financial services and retail industries."]
    }
    
    website_data = extract_company_intelligence(
        homepage_url="https://infosys.com",
        company_slug="infosys",
        page_metadata=page_metadata,
        combined_clean_text="Clean text content",
        combined_raw_text="Raw text content",
        classified_sections=classified,
        aggregated_contacts={"emails": ["contact@infosys.com"], "phone_numbers": ["+91 80 2852 0261"], "social_links": ["https://linkedin.com/company/infosys"]},
        discovered_pages={"about": "https://infosys.com/about", "contact": "https://infosys.com/contact"},
        social_links=["https://linkedin.com/company/infosys"],
        visited_urls=["https://infosys.com"],
        crawl_duration=1.5
    )
    
    assert isinstance(website_data, WebsiteData)
    assert website_data.company_name == "Infosys"
    assert website_data.company_slug == "infosys"
    assert website_data.emails == ["contact@infosys.com"]
    assert "Salil Parekh" in website_data.leadership
    assert "Finacle banking platform" in website_data.products


# ===========================================================================
# 4. Orchestrator Input Classification & Graph Routing Tests
# ===========================================================================

def test_orchestrator_input_classifier():
    # Test dual URL input (website and linkedin)
    state_both = {"user_input": "https://infosys.com, https://linkedin.com/company/infosys"}
    result_both = classify_input(state_both)
    assert result_both["input_type"] == "both_urls"
    assert result_both["website_url"] == "https://infosys.com"
    assert result_both["linkedin_url"] == "https://linkedin.com/company/infosys"
    assert result_both["company_slug"] == "infosys"

    # Test single website URL
    state_web = {"user_input": "https://infosys.com"}
    result_web = classify_input(state_web)
    assert result_web["input_type"] == "website_url"
    assert result_web["website_url"] == "https://infosys.com"
    assert result_web["company_slug"] == "infosys"

    # Test single LinkedIn URL
    state_li = {"user_input": "https://www.linkedin.com/company/infosys"}
    result_li = classify_input(state_li)
    assert result_li["input_type"] == "linkedin_url"
    assert result_li["linkedin_url"] == "https://www.linkedin.com/company/infosys"
    assert result_li["company_slug"] == "infosys"

    # Test company name plain text
    state_name = {"user_input": "Infosys Technologies"}
    result_name = classify_input(state_name)
    assert result_name["input_type"] == "company_name"
    assert result_name["company_name"] == "Infosys Technologies"


def test_orchestrator_graph_compile():
    graph = build_graph()
    assert graph is not None
    # Verify graph can compile and contains the correct nodes
    assert "classify_input" in graph.nodes
    assert "trigger_scrapers" in graph.nodes
    assert "run_website_agent" in graph.nodes
    assert "run_linkedin_agent" in graph.nodes
    assert "merge_results" in graph.nodes


# ===========================================================================
# 5. Routing and Edge-case Tests
# ===========================================================================

from orchestrator.graph import _route_after_classify, _route_after_website_discovery

def test_routing_logic():
    # Test routing after classification
    assert _route_after_classify({"input_type": "both_urls"}) == "trigger_scrapers"
    assert _route_after_classify({"input_type": "website_url"}) == "discover_from_website"
    assert _route_after_classify({"input_type": "linkedin_url"}) == "discover_website"
    assert _route_after_classify({"input_type": "company_name"}) == "discover_website"

    # Test routing after website discovery
    assert _route_after_website_discovery({"linkedin_url": "https://linkedin.com/company/test"}) == "trigger_scrapers"
    assert _route_after_website_discovery({"linkedin_url": None}) == "discover_linkedin"


def test_classify_input_edge_cases():
    # Test spaces and multi separators
    state_messy = {"user_input": "   https://infosys.com  ;   https://linkedin.com/company/infosys   "}
    res = classify_input(state_messy)
    assert res["input_type"] == "both_urls"
    assert res["website_url"] == "https://infosys.com"
    assert res["linkedin_url"] == "https://linkedin.com/company/infosys"

    # Test empty or invalid
    assert classify_input({"user_input": "    "})["input_type"] == "company_name"


def test_identify_role_pages():
    pages = {
        "https://infosys.com/about-us": "About page content",
        "https://infosys.com/careers/jobs": "Careers content",
        "https://infosys.com/get-in-touch": "Contact content",
        "https://infosys.com/blog/article-1": "Blog content",
    }
    role_pages = identify_role_pages(list(pages.keys()))
    assert role_pages["about"] == "https://infosys.com/about-us"
    assert role_pages["careers"] == "https://infosys.com/careers/jobs"
    assert role_pages["contact"] == "https://infosys.com/get-in-touch"
    assert role_pages["blog"] == "https://infosys.com/blog/article-1"
