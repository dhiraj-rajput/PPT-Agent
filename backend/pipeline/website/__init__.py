"""
website/__init__.py
-------------------
Public API for the website scraping module.

This module crawls a company's official website using Playwright,
extracts structured business intelligence, and stores it in MongoDB.

Usage:
    from pipeline.website import scrape_website, WebsiteData
"""

from pipeline.website.crawler import crawl_website
from pipeline.website.pipeline import WebsitePipeline
from pipeline.website.models import WebsiteData, CrawlMetadata
from pipeline.website.storage import WebsiteStorage

__all__ = [
    "crawl_website",
    "WebsitePipeline",
    "WebsiteData",
    "CrawlMetadata",
    "WebsiteStorage",
]
