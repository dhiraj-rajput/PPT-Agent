"""
config/settings.py
------------------
Central application settings loaded from environment variables.

Uses pydantic-settings so every field is:
  - Type-validated at startup
  - Sourced from the .env file automatically
  - Accessible as a typed Python object (no raw os.getenv calls)

Usage:
    from config.settings import settings

    settings.MONGO_URI
    settings.OPENROUTER_API_KEY
    settings.OPENROUTER_MODEL
    ...
"""

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field


class AppSettings(BaseSettings):
    """
    All application-wide settings.
    Values are read from environment variables or the .env file.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # ------------------------------------------------------------------
    # MongoDB
    # ------------------------------------------------------------------
    MONGO_URI: str = Field(
        default="mongodb://localhost:27017/",
        description=(
            "MongoDB connection string.\n"
            "  Local:  mongodb://localhost:27017/\n"
            "  Atlas:  mongodb+srv://<user>:<pass>@<cluster>.mongodb.net/?retryWrites=true&w=majority"
        ),
    )
    MONGO_DB_NAME: str = Field(
        default="ppt_agent_db",
        description="Name of the MongoDB database to use.",
    )



    # ------------------------------------------------------------------
    # Search — Tavily (company name → LinkedIn URL resolution)
    # ------------------------------------------------------------------
    TAVILY_API_KEY: str = Field(
        default="",
        description="Tavily search API key. Get one at https://app.tavily.com",
    )

    # ------------------------------------------------------------------
    # LinkedIn Authenticated Scraping (Optional)
    # ------------------------------------------------------------------
    LINKEDIN_LI_AT: str = Field(
        default="",
        description=(
            "LinkedIn li_at session cookie for authenticated scraping. "
            "See linkedin/GUIDE.md for instructions. "
            "Leave empty to run in public-only mode."
        ),
    )

    # ------------------------------------------------------------------
    # Scraping Behavior
    # ------------------------------------------------------------------
    SCRAPE_DELAY_MIN_SECONDS: float = Field(
        default=3.0,
        description="Minimum delay in seconds between scraping requests.",
    )
    SCRAPE_DELAY_MAX_SECONDS: float = Field(
        default=8.0,
        description="Maximum delay in seconds between scraping requests.",
    )
    BROWSER_HEADLESS: bool = Field(
        default=True,
        description="Run Playwright browser in headless mode (set False to debug visually).",
    )

    # ------------------------------------------------------------------
    # Website Crawler (prasanna/company-extractor settings)
    # ------------------------------------------------------------------
    MAX_CRAWL_PAGES: int = Field(
        default=15,
        description="Maximum number of pages to crawl per company website.",
    )
    CRAWL_TIMEOUT: int = Field(
        default=30000,
        description="Playwright page load timeout in milliseconds.",
    )


    SAM_GOV_API_KEY: str = Field(default="", description="SAM.gov API key.")
    FORCE_MOCK_SAM_GOV: bool = Field(default=False, description="Force SAM.gov to use mock data instead of live queries.")

    # ------------------------------------------------------------------
    # Optional / Other Search & Scraping Services
    # ------------------------------------------------------------------
    SERPAPI_API_KEY: str = Field(default="", description="SerpAPI key (fallback search).")
    FIRECRAWL_API_KEY: str = Field(default="", description="Firecrawl API key.")

    # ------------------------------------------------------------------
    # MongoDB Collections & Search Settings
    # ------------------------------------------------------------------
    MONGODB_RAW_COLLECTION: str = Field(default="raw_data")
    MONGODB_CLEANED_COLLECTION: str = Field(default="cleaned_data")
    MONGODB_PROFILE_COLLECTION: str = Field(default="company_profiles")
    SEARCH_PROVIDER: str = Field(default="auto")

    # ------------------------------------------------------------------
    # Ollama LLM Configuration (free cloud model)
    # ------------------------------------------------------------------
    OLLAMA_HOST: str = Field(
        default="",
        description="Ollama host URL. Leave empty to use local Ollama (http://localhost:11434).",
    )
    OLLAMA_MODEL: str = Field(
        default="gemma4:31b-cloud",
        description="Ollama model to use for LLM compaction and RFP response generation.",
    )
    OLLAMA_API_KEY: str = Field(
        default="",
        description="Optional API key for authenticated hosted Ollama cloud endpoints.",
    )
    OPENROUTER_API_KEY: str = Field(
        default="",
        description="[Deprecated] OpenRouter API key. Use Ollama instead.",
    )
    OPENROUTER_BASE_URL: str = Field(
        default="https://openrouter.ai/api/v1",
        description="[Deprecated] OpenRouter base URL.",
    )
    OPENROUTER_MODEL: str = Field(
        default="google/gemma-4-31b-it:free",
        description="[Deprecated] OpenRouter model name.",
    )

    @property
    def is_authenticated_linkedin_scraping_enabled(self) -> bool:
        """Returns True if the LinkedIn li_at cookie is configured and not a placeholder."""
        val = getattr(self, "LINKEDIN_LI_AT", "").strip()
        if not val or "your_" in val or "placeholder" in val or val == "li_at":
            return False
        return True

    @property
    def is_tavily_search_enabled(self) -> bool:
        """Returns True if the Tavily API key is configured."""
        return bool(self.TAVILY_API_KEY)

    # --- Case-insensitive property mappings for codebase compatibility ---
    @property
    def mongodb_uri(self) -> str:
        return self.MONGO_URI

    @property
    def mongodb_db_name(self) -> str:
        return self.MONGO_DB_NAME

    @property
    def raw_collection(self) -> str:
        return self.MONGODB_RAW_COLLECTION

    @property
    def cleaned_collection(self) -> str:
        return self.MONGODB_CLEANED_COLLECTION

    @property
    def profile_collection(self) -> str:
        return self.MONGODB_PROFILE_COLLECTION



    @property
    def search_provider(self) -> str:
        return self.SEARCH_PROVIDER.strip().lower()

    @property
    def tavily_api_key(self) -> str:
        return self.TAVILY_API_KEY

    @property
    def serpapi_api_key(self) -> str:
        return self.SERPAPI_API_KEY

    @property
    def ollama_host(self) -> str:
        if not self.OLLAMA_HOST and self.OLLAMA_API_KEY:
            return "https://ollama.com"
        return self.OLLAMA_HOST

    @property
    def ollama_model(self) -> str:
        return self.OLLAMA_MODEL

    @property
    def ollama_api_key(self) -> str:
        return self.OLLAMA_API_KEY


class ConfigurationError(RuntimeError):
    """Raised when required configuration is missing."""


# Type alias for external modules
Settings = AppSettings


# Module-level singleton — import this everywhere
settings = AppSettings()


def load_settings(env_path=None) -> AppSettings:
    """Return the global Settings instance."""
    return settings
