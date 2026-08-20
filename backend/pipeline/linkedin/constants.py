"""
linkedin/constants.py
---------------------
LinkedIn-specific constants used across all LinkedIn module files.

Centralizing these here means:
  - One place to update when LinkedIn changes its URL structure or selectors
  - No magic strings scattered across the codebase
  - Easy to read and maintain
"""

# ---------------------------------------------------------------------------
# LinkedIn Base URLs
# ---------------------------------------------------------------------------

LINKEDIN_BASE_URL = "https://www.linkedin.com"
LINKEDIN_COMPANY_BASE_URL = f"{LINKEDIN_BASE_URL}/company"

# Sub-page paths appended to the company URL
LINKEDIN_COMPANY_ABOUT_PATH = "about"
LINKEDIN_COMPANY_POSTS_PATH = "posts"
LINKEDIN_COMPANY_JOBS_PATH = "jobs"
LINKEDIN_COMPANY_PEOPLE_PATH = "people"
LINKEDIN_COMPANY_INSIGHTS_PATH = "insights"


def build_company_page_url(company_slug: str) -> str:
    """Returns the main company page URL for the given slug."""
    return f"{LINKEDIN_COMPANY_BASE_URL}/{company_slug}"


def build_company_about_url(company_slug: str) -> str:
    """Returns the About section URL for the given company slug."""
    return f"{LINKEDIN_COMPANY_BASE_URL}/{company_slug}/{LINKEDIN_COMPANY_ABOUT_PATH}"


def build_company_posts_url(company_slug: str) -> str:
    """Returns the Posts feed URL for the given company slug."""
    return f"{LINKEDIN_COMPANY_BASE_URL}/{company_slug}/{LINKEDIN_COMPANY_POSTS_PATH}"


def build_company_jobs_url(company_slug: str) -> str:
    """Returns the Jobs listing URL for the given company slug."""
    return f"{LINKEDIN_COMPANY_BASE_URL}/{company_slug}/{LINKEDIN_COMPANY_JOBS_PATH}"


def build_company_people_url(company_slug: str) -> str:
    """Returns the People/Employees URL for the given company slug."""
    return f"{LINKEDIN_COMPANY_BASE_URL}/{company_slug}/{LINKEDIN_COMPANY_PEOPLE_PATH}"


# ---------------------------------------------------------------------------
# HTTP Request Headers
# ---------------------------------------------------------------------------

# Rotate between multiple User-Agent strings to appear as different browsers.
# These represent real, modern browser versions to avoid simple UA-based detection.
USER_AGENT_POOL = [
    (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    ),
    (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:126.0) "
        "Gecko/20100101 Firefox/126.0"
    ),
    (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) "
        "Version/17.4.1 Safari/605.1.15"
    ),
]

# Standard headers for unauthenticated requests
PUBLIC_REQUEST_HEADERS = {
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;"
        "q=0.9,image/avif,image/webp,*/*;q=0.8"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Cache-Control": "max-age=0",
}


# ---------------------------------------------------------------------------
# Company Size Range Mappings
# ---------------------------------------------------------------------------

# LinkedIn uses codes to represent employee count ranges.
# These are the human-readable labels displayed on company profiles.
COMPANY_SIZE_CODE_TO_LABEL = {
    "A": "1 employee",
    "B": "2-10 employees",
    "C": "11-50 employees",
    "D": "51-200 employees",
    "E": "201-500 employees",
    "F": "501-1,000 employees",
    "G": "1,001-5,000 employees",
    "H": "5,001-10,000 employees",
    "I": "10,001+ employees",
}

# Reverse map: label → code (for normalization)
COMPANY_SIZE_LABEL_TO_CODE = {v: k for k, v in COMPANY_SIZE_CODE_TO_LABEL.items()}


# ---------------------------------------------------------------------------
# Scraping Layer Names
# ---------------------------------------------------------------------------
# Used to tag raw scraped documents with the layer that produced them.

SCRAPE_LAYER_PUBLIC = "public"           # Layer 1: No login, basic HTML
SCRAPE_LAYER_BROWSER = "browser"           # Layer 2: Playwright browser scraping
SCRAPE_LAYER_AUTHENTICATED = "authenticated"  # Layer 3: li_at session cookie


# ---------------------------------------------------------------------------
# MongoDB Collection Names
# ---------------------------------------------------------------------------

COLLECTION_RAW_LINKEDIN = "raw_linkedin"
COLLECTION_STRUCTURED_LINKEDIN = "structured_linkedin"
COLLECTION_SCRAPE_LOGS = "scrape_logs"


# ---------------------------------------------------------------------------
# Tavily Search Configuration
# ---------------------------------------------------------------------------

# Search query template used to find a company's LinkedIn URL
# given only its name. {company_name} is replaced at runtime.
TAVILY_LINKEDIN_SEARCH_QUERY_TEMPLATE = (
    'site:linkedin.com/company "{company_name}" official company page'
)

# Maximum number of Tavily search results to consider
TAVILY_MAX_SEARCH_RESULTS = 5
