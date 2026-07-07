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
    # LLM Provider — OpenRouter
    # ------------------------------------------------------------------
    OPENROUTER_API_KEY: str = Field(
        default="",
        description="OpenRouter API key. Get one at https://openrouter.ai/keys",
    )
    OPENROUTER_MODEL: str = Field(
        default="google/gemma-4-31b-it:free",
        description=(
            "OpenRouter model ID. Set in .env to override.\n"
            "Confirmed FREE models (check https://openrouter.ai/models?q=free):\n"
            "  google/gemma-4-31b-it:free   ← default, confirmed working (16 req/min limit)\n"
            "  google/gemma-3-27b-it:free   ← Gemma 3, higher limits\n"
            "  mistralai/mistral-7b-instruct:free\n"
            "  qwen/qwen3-8b:free\n"
            "NOTE: Meta Llama 3.1 :free no longer exists — use paid slug without :free suffix."
        ),
    )
    OPENROUTER_BASE_URL: str = Field(
        default="https://openrouter.ai/api/v1",
        description="OpenRouter API base URL (OpenAI-compatible).",
    )
    USE_LLM_STRUCTURING: bool = Field(
        default=False,
        description=(
            "If True, the system will use LLM/AI (via OpenRouter) to structure raw data and extract BI.\n"
            "If False, the system uses high-performance, cost-free, deterministic rule-based regex parsing."
        ),
    )
    LLM_INTER_CALL_DELAY_SECONDS: float = Field(
        default=4.0,
        description=(
            "Seconds to wait between consecutive LLM calls inside the structurer. "
            "Free models allow ~16 req/min. 4s keeps us safely under that limit."
        ),
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

    # ------------------------------------------------------------------
    # Optional / Future LLM Providers
    # ------------------------------------------------------------------
    GEMINI_API_KEY: str = Field(default="", description="Google Gemini API key.")
    OPENAI_API_KEY: str = Field(default="", description="OpenAI API key.")

    # ------------------------------------------------------------------
    # Optional / Other Search & Scraping Services
    # ------------------------------------------------------------------
    SERPAPI_API_KEY: str = Field(default="", description="SerpAPI key (fallback search).")
    FIRECRAWL_API_KEY: str = Field(default="", description="Firecrawl API key.")

    # ------------------------------------------------------------------
    # Hugging Face & Extra Search / Collection Settings (Nitin branch)
    # ------------------------------------------------------------------
    MONGODB_RAW_COLLECTION: str = Field(default="raw_data")
    MONGODB_CLEANED_COLLECTION: str = Field(default="cleaned_data")
    MONGODB_PROFILE_COLLECTION: str = Field(default="company_profiles")
    LLM_PROVIDER: str = Field(default="huggingface")
    HF_TOKEN: str = Field(default="")
    HF_MODEL_ID: str = Field(default="google/gemma-4-31B-it")
    HF_INFERENCE_PROVIDER: str = Field(default="auto")
    SEARCH_PROVIDER: str = Field(default="auto")

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

    # --- Case-insensitive property mappings for Nitin's codebase compatibility ---
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
    def llm_provider(self) -> str:
        return self.LLM_PROVIDER.strip().lower()

    @property
    def hf_token(self) -> str:
        return self.HF_TOKEN

    @property
    def hf_model_id(self) -> str:
        return self.HF_MODEL_ID

    @property
    def hf_provider(self) -> str:
        return self.HF_INFERENCE_PROVIDER

    @property
    def search_provider(self) -> str:
        return self.SEARCH_PROVIDER.strip().lower()

    @property
    def tavily_api_key(self) -> str:
        return self.TAVILY_API_KEY

    @property
    def serpapi_api_key(self) -> str:
        return self.SERPAPI_API_KEY


class ConfigurationError(RuntimeError):
    """Raised when required configuration is missing."""


# Type alias for external modules
Settings = AppSettings


# Module-level singleton — import this everywhere
settings = AppSettings()


def load_settings(env_path=None) -> AppSettings:
    """Return the global Settings instance."""
    return settings
