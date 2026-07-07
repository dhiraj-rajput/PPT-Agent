"""
website/models.py
-----------------
Pydantic data models for all company website scraped data.

These models are the structured output from the website scraping pipeline
and are stored in the 'raw_website' and 'structured_website' MongoDB collections.
"""

from datetime import datetime
from typing import List, Optional, Dict
from pydantic import BaseModel, Field


class WebsiteData(BaseModel):
    """
    Structured intelligence extracted from a company's official website.
    Stored in the 'structured_website' MongoDB collection.
    """
    # --- Core Identity ---
    company_slug: str = Field(description="Unique slug derived from the domain (e.g. 'infosys' from infosys.com)")
    company_name: str = Field(default="", description="Name of the company extracted from page title / meta tags")
    website_url: str = Field(description="Homepage URL that was scraped")
    industry: str = Field(default="", description="Inferred industry/sector from website content")
    description: str = Field(default="", description="Brief company description from about/meta content")

    # --- Location ---
    headquarters: str = Field(default="", description="Primary headquarters location")
    locations: List[str] = Field(default_factory=list, description="All office/branch locations mentioned")

    # --- Offerings ---
    products: List[str] = Field(default_factory=list, description="Products offered by the company")
    services: List[str] = Field(default_factory=list, description="Services offered by the company")
    industries_served: List[str] = Field(default_factory=list, description="Industries/verticals the company serves")

    # --- People ---
    leadership: List[str] = Field(default_factory=list, description="Key leadership/executive names found on the site")
    technology_stack: List[str] = Field(default_factory=list, description="Technologies / frameworks detected")

    # --- Partnerships ---
    clients: List[str] = Field(default_factory=list, description="Notable customers or clients mentioned")
    partners: List[str] = Field(default_factory=list, description="Business partners mentioned")

    # --- Contact & Socials ---
    emails: List[str] = Field(default_factory=list, description="Contact email addresses found")
    phone_numbers: List[str] = Field(default_factory=list, description="Phone numbers found")
    social_links: List[str] = Field(default_factory=list, description="Social media profile links")
    linkedin_url: Optional[str] = Field(default=None, description="LinkedIn company page URL if found on the website")

    # --- Key Pages ---
    careers_page: str = Field(default="", description="URL of the careers/jobs page")
    blog_page: str = Field(default="", description="URL of the blog/news section")
    about_page: str = Field(default="", description="URL of the about page")
    contact_page: str = Field(default="", description="URL of the contact page")

    # --- Raw Content ---
    raw_text: str = Field(default="", description="Combined raw text across all crawled pages")
    clean_text: str = Field(default="", description="Cleaned main content text across all crawled pages")

    # --- Metadata ---
    scraped_at: datetime = Field(description="UTC timestamp when the scrape was completed")
    scrape_status: str = Field(default="success", description="'success', 'partial', or 'failed'")
    pages_crawled: int = Field(default=0, description="Number of pages successfully crawled")
    visited_urls: List[str] = Field(default_factory=list, description="List of all crawled URLs")

    class Config:
        json_encoders = {datetime: lambda dt: dt.isoformat()}


class RawWebsiteScrapedData(BaseModel):
    """
    Raw page content from a single crawled page. Stored in 'raw_website' collection.
    """
    company_slug: str
    page_url: str
    raw_html: Optional[str] = Field(default=None, description="Raw HTML (first 100KB)")
    raw_text: Optional[str] = Field(default=None, description="Extracted raw visible text")
    clean_text: Optional[str] = Field(default=None, description="Cleaned main body text")
    page_title: Optional[str] = Field(default=None, description="Page <title> content")
    meta_description: Optional[str] = Field(default=None, description="Meta description content")
    scraped_at: datetime
    scrape_success: bool = Field(default=True)
    error_message: Optional[str] = Field(default=None)

    class Config:
        json_encoders = {datetime: lambda dt: dt.isoformat()}


class CrawlMetadata(BaseModel):
    """Metadata about a crawl run, stored alongside the company record."""
    pages_visited: int = Field(default=0)
    crawl_duration_seconds: float = Field(default=0.0)
    status: str = Field(default="pending")
    visited_urls: List[str] = Field(default_factory=list)
