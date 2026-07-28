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
import os
import random
import time
import json
import traceback
from concurrent.futures import ThreadPoolExecutor
from logging.handlers import RotatingFileHandler
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

import uuid
from config.settings import settings

class MongoSemaphore:
    def __init__(self, name="subprocess_limit", max_leases=3):
        self.name = name
        self.max_leases = max_leases
        self.lease_id = None

    def __enter__(self):
        from utils.db_client import get_collection
        coll = get_collection("active_leases")
        stale_threshold = time.time() - 600
        try:
            coll.delete_many({"name": self.name, "timestamp": {"$lt": stale_threshold}})
        except Exception:
            pass

        self.lease_id = str(uuid.uuid4())
        while True:
            try:
                count = coll.count_documents({"name": self.name})
                if count < self.max_leases:
                    coll.insert_one({
                        "name": self.name,
                        "lease_id": self.lease_id,
                        "timestamp": time.time()
                    })
                    break
            except Exception:
                pass
            time.sleep(2.0)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.lease_id:
            try:
                from utils.db_client import get_collection
                coll = get_collection("active_leases")
                coll.delete_one({"lease_id": self.lease_id})
            except Exception:
                pass

SUBPROCESS_SEMAPHORE = MongoSemaphore("subprocess_limit", 3)

def get_python_executable() -> str:
    """
    Returns the configured python interpreter path, or sys.executable as a fallback.
    """
    import sys
    from config.settings import settings
    return settings.PYTHON_PATH or sys.executable


# ---------------------------------------------------------------------------
# Logging Setup
# ---------------------------------------------------------------------------

# Directory for on-disk logs — visible in cPanel File Manager / SSH regardless
# of whether Passenger's own stderr capture is exposed on a given hosting plan.
_LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs")
try:
    os.makedirs(_LOG_DIR, exist_ok=True)
except Exception:
    pass

# Small dedicated thread pool so writing a log entry to MongoDB never blocks
# the request/event loop that triggered it.
_ERROR_LOG_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="error-log-writer")


class MongoErrorLogHandler(logging.Handler):
    """
    Logging handler that persists WARNING/ERROR/CRITICAL records to the
    `error_logs` MongoDB collection so they can be browsed, filtered, and
    resolved from the in-app Server Logs admin page instead of relying on
    hosting-panel log viewers.

    The actual insert is dispatched to a background thread so a logging
    call never adds latency to the request that triggered it, and any
    failure to reach MongoDB is swallowed (a logging handler must never be
    the thing that crashes the app).
    """

    def emit(self, record: logging.LogRecord) -> None:
        try:
            detail = ""
            if record.exc_info:
                detail = "".join(traceback.format_exception(*record.exc_info))
            elif record.stack_info:
                detail = str(record.stack_info)

            doc = {
                "timestamp": datetime.now(timezone.utc),
                "level": record.levelname,
                "source": record.name,
                "message": record.getMessage(),
                "detail": detail,
                "path": getattr(record, "path", None),
                "method": getattr(record, "method", None),
                "statusCode": getattr(record, "status_code", None),
                "userEmail": getattr(record, "user_email", None),
                "ip": getattr(record, "client_ip", None),
                "module": record.module,
                "func": record.funcName,
                "line": record.lineno,
                "resolved": False,
            }
            _ERROR_LOG_EXECUTOR.submit(_write_error_log_doc, doc)
        except Exception:
            # A logging handler must never raise.
            pass


def _write_error_log_doc(doc: dict) -> None:
    """Runs on a background thread — inserts one error-log document into MongoDB."""
    try:
        # Imported lazily to avoid a circular import (db_client imports this module).
        from utils.db_client import get_collection
        get_collection("error_logs").insert_one(doc)
    except Exception:
        # If MongoDB is briefly unreachable, don't lose the process over a log line.
        pass


def setup_logger(logger_name: str) -> logging.Logger:
    """
    Creates and returns a logger with a clean, readable format that logs to:
      - the console (stdout/stderr — visible via `tail`/Passenger logs)
      - a rotating file at backend/logs/app.log (visible in cPanel File Manager)
      - MongoDB `error_logs` collection for WARNING and above (powers the
        in-app Server Logs admin page, live alert banner, etc.)

    Args:
        logger_name: Typically the module's __name__.

    Returns:
        A configured logging.Logger instance.

    Example:
        logger = setup_logger(__name__)
        logger.info("Scraping started", extra={"company_slug": "infosys"})
        logger.error("Upstream API failed", exc_info=True)
    """
    logger = logging.getLogger(logger_name)

    if logger.handlers:
        # Avoid adding duplicate handlers if setup_logger is called multiple times
        return logger

    logger.setLevel(logging.DEBUG)

    log_format = logging.Formatter(
        fmt="[%(asctime)s] %(levelname)-8s %(name)s — %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Console handler with a human-readable format
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.DEBUG)
    console_handler.setFormatter(log_format)
    logger.addHandler(console_handler)

    # Rotating file handler — 5MB x 5 backups, always on disk regardless of
    # how the hosting panel captures (or fails to capture) process stderr.
    try:
        file_handler = RotatingFileHandler(
            os.path.join(_LOG_DIR, "app.log"),
            maxBytes=5_000_000,
            backupCount=5,
            encoding="utf-8",
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(log_format)
        logger.addHandler(file_handler)
    except Exception:
        # Read-only filesystem edge case — console logging still works.
        pass

    # MongoDB handler — structured, queryable, powers the admin Server Logs page.
    mongo_handler = MongoErrorLogHandler()
    mongo_handler.setLevel(logging.WARNING)
    logger.addHandler(mongo_handler)

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
