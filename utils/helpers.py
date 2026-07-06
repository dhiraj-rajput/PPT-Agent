"""
utils/helpers.py
----------------
Shared utility functions used across all modules.

Includes:
  - Structured JSON logging setup
  - Retry decorator with exponential backoff (via tenacity)
  - Random delay helper for polite scraping
  - URL validation and normalization utilities
  - Date/time formatting helpers
"""

import logging
import random
import time
import json
from datetime import datetime, timezone
from functools import wraps
from typing import Any, Callable, TypeVar
from urllib.parse import urlparse

from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log,
)

from config.settings import settings


# ---------------------------------------------------------------------------
# Logging Setup
# ---------------------------------------------------------------------------

def setup_logger(logger_name: str) -> logging.Logger:
    """
    Creates and returns a logger with a clean, readable format.

    Args:
        logger_name: Typically the module's __name__.

    Returns:
        A configured logging.Logger instance.

    Example:
        logger = setup_logger(__name__)
        logger.info("Scraping started", extra={"company_slug": "infosys"})
    """
    logger = logging.getLogger(logger_name)

    if logger.handlers:
        # Avoid adding duplicate handlers if setup_logger is called multiple times
        return logger

    logger.setLevel(logging.DEBUG)

    # Console handler with a human-readable format
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.DEBUG)

    log_format = logging.Formatter(
        fmt="[%(asctime)s] %(levelname)-8s %(name)s — %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    console_handler.setFormatter(log_format)
    logger.addHandler(console_handler)

    return logger


# Module-level logger for this file
logger = setup_logger(__name__)


# ---------------------------------------------------------------------------
# Retry Decorator
# ---------------------------------------------------------------------------

# Generic TypeVar for decorated functions
FunctionType = TypeVar("FunctionType", bound=Callable[..., Any])


def retry_on_network_error(
    max_attempts: int = 3,
    wait_min_seconds: float = 2.0,
    wait_max_seconds: float = 10.0,
) -> Callable:
    """
    Decorator that retries a function on network-related exceptions
    with exponential backoff between retries.

    Args:
        max_attempts:       Maximum number of total attempts.
        wait_min_seconds:   Minimum wait time between retries.
        wait_max_seconds:   Maximum wait time between retries.

    Example:
        @retry_on_network_error(max_attempts=3)
        def fetch_page(url: str) -> str:
            ...
    """
    return retry(
        stop=stop_after_attempt(max_attempts),
        wait=wait_exponential(multiplier=1, min=wait_min_seconds, max=wait_max_seconds),
        retry=retry_if_exception_type((ConnectionError, TimeoutError, OSError)),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True,
    )


# ---------------------------------------------------------------------------
# Scraping Delay Helper
# ---------------------------------------------------------------------------

def wait_random_delay() -> None:
    """
    Pauses execution for a random duration between the configured
    SCRAPE_DELAY_MIN_SECONDS and SCRAPE_DELAY_MAX_SECONDS.

    This mimics human browsing behavior to reduce the chance of
    being detected and blocked by anti-scraping systems.

    The delay values come from the application settings (.env file).
    """
    delay_seconds = random.uniform(
        settings.SCRAPE_DELAY_MIN_SECONDS,
        settings.SCRAPE_DELAY_MAX_SECONDS,
    )
    logger.debug(f"Waiting {delay_seconds:.2f}s before next request...")
    time.sleep(delay_seconds)


# ---------------------------------------------------------------------------
# URL Utilities
# ---------------------------------------------------------------------------

def is_valid_url(url: str) -> bool:
    """
    Checks whether a string is a valid HTTP/HTTPS URL.

    Args:
        url: The string to check.

    Returns:
        True if the URL has a valid scheme and network location.

    Example:
        is_valid_url("https://linkedin.com/company/google")  # True
        is_valid_url("google")                               # False
    """
    try:
        parsed = urlparse(url)
        return parsed.scheme in ("http", "https") and bool(parsed.netloc)
    except ValueError:
        return False


def normalize_linkedin_company_url(raw_url: str) -> str:
    """
    Cleans and normalizes a LinkedIn company page URL.

    Removes query parameters, trailing slashes, and ensures
    the URL uses the canonical format:
        https://www.linkedin.com/company/<slug>

    Args:
        raw_url: Any LinkedIn company URL (possibly with query params or fragment).

    Returns:
        The normalized URL, e.g. "https://www.linkedin.com/company/infosys"

    Example:
        normalize_linkedin_company_url(
            "https://www.linkedin.com/company/infosys/?trk=..."
        )
        # Returns: "https://www.linkedin.com/company/infosys"
    """
    parsed = urlparse(raw_url)
    # Reconstruct with only scheme + netloc + path, stripping query and fragment
    clean_path = parsed.path.rstrip("/")
    normalized = f"https://www.linkedin.com{clean_path}"
    return normalized


def extract_company_slug_from_url(linkedin_url: str) -> str:
    """
    Extracts the company slug from a LinkedIn company URL.

    Args:
        linkedin_url: e.g. "https://www.linkedin.com/company/infosys"

    Returns:
        The slug string, e.g. "infosys"

    Raises:
        ValueError: If the URL does not follow the expected pattern.

    Example:
        extract_company_slug_from_url("https://www.linkedin.com/company/google")
        # Returns: "google"
    """
    parsed = urlparse(linkedin_url)
    path_parts = [part for part in parsed.path.split("/") if part]

    # Expected path: ["company", "<slug>"]
    if len(path_parts) >= 2 and path_parts[0] == "company":
        return path_parts[1]

    raise ValueError(
        f"Could not extract company slug from URL: {linkedin_url}. "
        "Expected format: https://www.linkedin.com/company/<slug>"
    )


# ---------------------------------------------------------------------------
# Date/Time Helpers
# ---------------------------------------------------------------------------

def get_utc_now() -> datetime:
    """Returns the current UTC timestamp as a timezone-aware datetime object."""
    return datetime.now(tz=timezone.utc)


def format_datetime_for_display(dt: datetime) -> str:
    """
    Formats a datetime object as a human-readable ISO 8601 string.

    Args:
        dt: A datetime object (timezone-aware or naive).

    Returns:
        A string like "2026-07-06T12:00:00Z"
    """
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# Data Serialization Helpers
# ---------------------------------------------------------------------------

def safe_json_dumps(data: Any, indent: int = 2) -> str:
    """
    Converts a Python object to a JSON string safely.
    Handles datetime objects and other non-serializable types.

    Args:
        data:   The object to serialize.
        indent: JSON indentation level.

    Returns:
        A JSON-formatted string.
    """

    def _json_serializer(obj: Any) -> str:
        if isinstance(obj, datetime):
            return format_datetime_for_display(obj)
        raise TypeError(f"Object of type {type(obj)} is not JSON serializable")

    return json.dumps(data, default=_json_serializer, indent=indent, ensure_ascii=False)
