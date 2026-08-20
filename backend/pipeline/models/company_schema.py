"""
models/company_schema.py
------------------------
Pydantic data models used across the PPT-Agent pipeline.

Models:
    CompanyIntelligence     — structured output from the website crawler/extractor
    CrawlMetadata           — crawl execution statistics
    CompanyMongoRecord      — wrapper stored in MongoDB by the website pipeline
    OptimizedCompanyProfile — final unified competitor-intelligence profile produced by the compactor
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Website Pipeline models (from compactor branch — company_schema.py)
# ---------------------------------------------------------------------------

class CompanyIntelligence(BaseModel):
    """Structured intelligence extracted from crawling a company website."""

    company_name: str = Field(default="", description="Name of the company")
    website: str = Field(default="", description="Website homepage URL")
    industry: str = Field(default="", description="Industry or sector of the company")
    description: str = Field(default="", description="Brief description of the company")
    headquarters: str = Field(default="", description="Corporate headquarters location")
    locations: List[str] = Field(default_factory=list, description="All locations / offices")
    products: List[str] = Field(default_factory=list, description="Products offered")
    services: List[str] = Field(default_factory=list, description="Services offered")
    industries_served: List[str] = Field(default_factory=list, description="Target industries")
    leadership: List[str] = Field(default_factory=list, description="Key executive members")
    technology_stack: List[str] = Field(default_factory=list, description="Technologies detected")
    clients: List[str] = Field(default_factory=list, description="Notable clients")
    partners: List[str] = Field(default_factory=list, description="Business partners")
    emails: List[str] = Field(default_factory=list, description="Contact emails")
    phone_numbers: List[str] = Field(default_factory=list, description="Contact phone numbers")
    social_links: List[str] = Field(default_factory=list, description="Official social profiles")
    careers_page: str = Field(default="", description="URL of the careers page")
    blog_page: str = Field(default="", description="URL of the blog/news section")
    about_page: str = Field(default="", description="URL of the about page")
    contact_page: str = Field(default="", description="URL of the contact page")
    raw_text: str = Field(default="", description="Combined raw text from crawled pages")
    clean_text: str = Field(default="", description="Combined clean text from crawled pages")
    scraped_at: str = Field(default="", description="ISO datetime of scrape completion")


class CrawlMetadata(BaseModel):
    """Statistics from a website crawl run."""

    pages_visited: int = Field(default=0, description="Total pages successfully parsed")
    crawl_time: str = Field(default="0s", description="Total crawl duration (HH:MM:SS)")
    status: str = Field(default="pending", description="success | partial | failed")
    visited_urls: List[str] = Field(default_factory=list, description="All visited URLs")


class CompanyMongoRecord(BaseModel):
    """MongoDB document wrapping a single website crawl result."""

    website: str = Field(..., description="Target homepage URL")
    company_data: CompanyIntelligence = Field(..., description="Extracted company intelligence")
    crawl_metadata: CrawlMetadata = Field(..., description="Crawl execution statistics")


# ---------------------------------------------------------------------------
# Final unified profile — produced by the compactor from all three agents
# ---------------------------------------------------------------------------

class OptimizedCompanyProfile(BaseModel):
    """
    Final unified competitor/RFP intelligence profile produced by the compactor.

    Aggregates data from:
      - Website crawler (WebsiteData)
      - LinkedIn scraper (LinkedInCompanyData)
      - External news / Google search (ExternalSearchClient)

    Designed for use in:
      - RFP (Request for Proposal) competitive analysis
      - Company profiling for business development
      - Competitive intelligence reports
    """

    # --- Identity ---
    # Defaults (not required) so partial agent output never fails validation;
    # empty strings mean "not found in sources" — never invent values to fill them.
    company_name: str = Field("", description="Normalised legal/commercial name of the company")
    website: str = Field("", description="Target homepage URL")
    industry: str = Field("", description="Consolidated industry categorisation")
    description: str = Field("", description="Clear, professional company description synthesising all sources")
    headquarters: str = Field("", description="Primary corporate headquarters location")
    locations: List[str] = Field(default_factory=list, description="All other office locations or operating markets")
    employee_count: str = Field("", description="Estimated workforce size (e.g. from LinkedIn or Google)")
    founded_year: Optional[int] = Field(None, description="Year the company was founded")
    specialties: List[str] = Field(default_factory=list, description="Core business specialties or taglines")

    # --- Products & Services ---
    products: List[str] = Field(default_factory=list, description="Key products offered (semantic names only, no fragments)")
    services: List[str] = Field(default_factory=list, description="Key services offered (semantic names only)")
    technology_stack: List[str] = Field(default_factory=list, description="Technologies used or offered")

    # --- Business Model & Revenue ---
    business_model: str = Field("", description="How the company makes money (e.g. SaaS, project-based, product sales)")
    pricing_model: str = Field("", description="Pricing approach (e.g. enterprise licence, subscription, per-project)")
    financial_highlights: List[str] = Field(
        default_factory=list,
        description="Key financial metrics: revenue figures, growth rates, funding rounds, profitability with dates"
    )

    # --- People ---
    leadership: List[str] = Field(default_factory=list, description="Consolidated executives / leadership team members")

    # --- Competitive Intelligence ---
    competitors: List[str] = Field(
        default_factory=list,
        description="Identified direct or indirect competitors with brief context (company name + why they compete)"
    )
    value_proposition: str = Field("", description="Synthesised unique selling proposition")
    rfp_strengths: List[str] = Field(
        default_factory=list,
        description="Strengths relevant to winning RFP / proposals (delivery track record, certifications, client wins)"
    )
    rfp_weaknesses: List[str] = Field(
        default_factory=list,
        description="Weaknesses or risks in RFP context (size, geography, known issues)"
    )
    opportunities: List[str] = Field(default_factory=list, description="Market opportunities identified")
    challenges: List[str] = Field(default_factory=list, description="Business challenges or risk factors")

    # --- Recent News ---
    recent_news: List[str] = Field(
        default_factory=list,
        description="Recent announcements, press releases, or news headlines (with approximate date if known)"
    )

    # --- Clients & Partners ---
    clients: List[str] = Field(default_factory=list, description="Notable customers or clients")
    partners: List[str] = Field(default_factory=list, description="Business partners or alliances")

    # --- Contact ---
    emails: List[str] = Field(default_factory=list, description="Consolidated contact emails")
    phone_numbers: List[str] = Field(default_factory=list, description="Consolidated contact phone numbers (E.164 or national format)")
    social_links: List[str] = Field(default_factory=list, description="Links to official LinkedIn, Twitter/X, YouTube, etc.")

    # --- Metadata ---
    sources_used: List[str] = Field(default_factory=list, description="Sources combined (e.g. Website, LinkedIn, Google)")
    last_updated: str = Field("", description="ISO 8601 UTC datetime of compilation")
