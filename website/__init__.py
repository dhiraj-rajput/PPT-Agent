"""
website/__init__.py
-------------------
Public API for the website scraping module.

This module crawls a company's official website using Playwright,
extracts structured business intelligence, and stores it in MongoDB.

Usage:
    from website import scrape_website, WebsiteData
"""

from website.crawler import crawl_website
from website.pipeline import WebsitePipeline
from website.models import WebsiteData, CrawlMetadata
from website.storage import WebsiteStorage

__all__ = [
    "crawl_website",
    "WebsitePipeline",
    "WebsiteData",
    "CrawlMetadata",
    "WebsiteStorage",
]
