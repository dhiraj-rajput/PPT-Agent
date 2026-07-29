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
    settings.AI_MODE
    settings.OLLAMA_MODEL
    ...
"""

from typing import Any, Union
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, field_validator, AliasChoices


class AppSettings(BaseSettings):
    """
    All application-wide settings.
    Values are read from environment variables or the .env file.
    """

    model_config = SettingsConfigDict(
        env_file=(".env", "backend/.env", "../backend/.env"),
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # ------------------------------------------------------------------
    # MongoDB
    # ------------------------------------------------------------------
    MONGO_URI: str = Field(
        default="mongodb://localhost:27017/",
        validation_alias=AliasChoices("MONGO_URI", "MONGODB_URI"),
        description=(
            "MongoDB connection string.\n"
            "  Local:  mongodb://localhost:27017/\n"
            "  Atlas:  mongodb+srv://<user>:<pass>@<cluster>.mongodb.net/?retryWrites=true&w=majority"
        ),
    )
    MONGO_DB_NAME: str = Field(
        default="winbidai",
        validation_alias=AliasChoices("MONGO_DB_NAME", "MONGODB_DB_NAME"),
        description="Name of the MongoDB database to use.",
    )

    # ------------------------------------------------------------------
    # MySQL (dual-DB setup — relational data goes here, documents stay in Mongo)
    # ------------------------------------------------------------------
    MYSQL_HOST: str = Field(
        default="localhost",
        description="MySQL server hostname.",
    )
    MYSQL_PORT: int = Field(
        default=3306,
        description="MySQL server port.",
    )
    MYSQL_USER: str = Field(
        default="root",
        description="MySQL username.",
    )
    MYSQL_PASSWORD: str = Field(
        default="",
        description="MySQL password.",
    )
    MYSQL_DB: str = Field(
        default="winbidai",
        description="MySQL database name.",
    )
    MYSQL_URI: str = Field(
        default="",
        description=(
            "Full async MySQL connection string (mysql+aiomysql://...). "
            "When set, takes precedence over MYSQL_HOST/PORT/USER/PASSWORD/DB. "
            "Example: mysql+aiomysql://user:pass@host:3306/winbidai"
        ),
    )
    MYSQL_URI_SYNC: str = Field(
        default="",
        description=(
            "Full sync MySQL connection string (mysql+pymysql://...) for background workers. "
            "Auto-derived from MYSQL_URI when not set."
        ),
    )
    MYSQL_POOL_SIZE: int = Field(
        default=5,
        description="SQLAlchemy async pool size for MySQL.",
    )
    MYSQL_MAX_OVERFLOW: int = Field(
        default=10,
        description="SQLAlchemy max pool overflow for MySQL.",
    )
    MYSQL_ECHO: bool = Field(
        default=False,
        description="Echo all SQL statements to the logger (dev only).",
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
    BROWSERLESS_CDP_URL: str = Field(
        default="",
        description=(
            "Optional wss:// CDP endpoint (e.g. Browserless.io, ScrapingBee, Crawlbase). "
            "When set, Playwright connects to this remote browser via connect_over_cdp() "
            "instead of launching a local Chromium binary — needed on hosts like cPanel "
            "that can't install/run Chrome system libraries."
        ),
    )

    # ------------------------------------------------------------------
    # Website Crawler
    # ------------------------------------------------------------------
    MAX_CRAWL_PAGES: int = Field(
        default=15,
        description="Maximum number of pages to crawl per company website.",
    )
    CRAWL_TIMEOUT: int = Field(
        default=30000,
        description="Playwright page load timeout in milliseconds.",
    )
    PYTHON_PATH: str = Field(
        default="",
        description="Path to the virtual environment python interpreter. Falls back to sys.executable if empty.",
    )

    # ------------------------------------------------------------------
    # SAM.gov
    # ------------------------------------------------------------------
    SAM_GOV_API_KEY: str = Field(default="", description="SAM.gov API key.")
    FORCE_MOCK_SAM_GOV: bool = Field(
        default=False,
        description="Force SAM.gov to use mock data instead of live queries.",
    )

    # ------------------------------------------------------------------
    # Optional / Other Search & Scraping Services
    # ------------------------------------------------------------------
    SERPAPI_API_KEY: str = Field(default="", description="SerpAPI key (fallback search).")
    FIRECRAWL_API_KEY: str = Field(default="", description="Firecrawl API key.")

    # ------------------------------------------------------------------
    # OCR Configuration
    # ------------------------------------------------------------------
    OCR_SPACE_API_KEY: str = Field(
        default="",
        description=(
            "OCR.space API key for cloud-based OCR (zero local computation). "
            "Free tier: 25,000 requests/month. "
            "Get a free key at https://ocr.space/ocrapi/freekey. "
            "Without a key, falls back to 500 req/day demo mode."
        ),
    )
    OCR_ENGINE: str = Field(
        default="auto",
        description=(
            "OCR engine to use: 'auto' (cascade: ocrspace -> pymupdf -> docling -> tesseract), "
            "'ocrspace' (cloud only), 'pymupdf' (digital PDFs only), "
            "'docling' (local), 'tesseract' (local)."
        ),
    )

    # ------------------------------------------------------------------
    # SAM.gov & Integrations
    # ------------------------------------------------------------------
    SAM_GOV_API_URL: str = Field(
        default="https://api.sam.gov/opportunities/v2/search",
        description="SAM.gov opportunities search API endpoint URL."
    )

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
        default="gemma4:e4b",
        description="Ollama model to use for LLM generation. Default is gemma4:e4b (edge-optimized, runs on 8GB RAM).",
    )
    OLLAMA_API_KEY: str = Field(
        default="",
        description="Optional API key for authenticated hosted Ollama cloud endpoints.",
    )
    OLLAMA_MODEL_FALLBACKS: str = Field(
        default="gemma4:e4b,gemma3:4b,gemma4:31b-cloud,llama3.1:8b",
        description="Comma-separated Ollama model fallback chain, tried in order after OLLAMA_MODEL.",
    )
    OLLAMA_TEMPERATURE: float = Field(
        default=0.1,
        description="Sampling temperature used for all Ollama Cloud calls.",
    )
    GEMINI_API_KEY: str = Field(
        default="",
        description="Google AI Studio Gemini API Key for fallback generation.",
    )
    OPENROUTER_API_KEY: str = Field(
        default="",
        description="OpenRouter API Key for fallback generation.",
    )
    OPENROUTER_MODEL: str = Field(
        default="google/gemini-2.5-flash",
        description="Primary OpenRouter model. Falls back through OPENROUTER_MODEL_FALLBACKS.",
    )
    OPENROUTER_MODEL_FALLBACKS: str = Field(
        default="meta-llama/llama-3.3-70b-instruct,mistralai/mistral-large-2411,openrouter/auto",
        description="Comma-separated OpenRouter model fallback chain, tried in order after OPENROUTER_MODEL.",
    )
    OPENROUTER_BASE_URL: str = Field(
        default="https://openrouter.ai/api/v1",
        description="OpenRouter base URL.",
    )
    AI_PROVIDER_ORDER: str = Field(
        default="gemini,openrouter,ollama",
        description=(
            "Comma-separated provider preference order (default: 'gemini,openrouter,ollama')."
        ),
    )

    # ------------------------------------------------------------------
    # Global AI / rule-based master switch
    # ------------------------------------------------------------------
    AI_MODE: str = Field(
        default="auto",
        description=(
            "Master switch for every agent in the project: "
            "'ai' or 'auto' = try AI (Ollama Cloud) first, automatically fall back to "
            "the rule-based implementation on failure or 429 rate-limit; "
            "'rule_based' = never call AI, always use rule-based logic."
        ),
    )

    # BYPASS_LLM: legacy env flag — kept for backwards compat. Prefer AI_MODE=rule_based.
    # When true, forces rule-based compaction regardless of AI_MODE.
    BYPASS_LLM: bool = Field(
        default=False,
        description=(
            "Legacy flag — forces rule-based compaction when True. "
            "Prefer setting AI_MODE=rule_based instead."
        ),
    )

    # Optional per-agent overrides. Any of these, if set to "ai" or
    # "rule_based", take precedence over AI_MODE for that agent only.
    WEBSITE_AGENT_MODE: str = Field(default="", description="Per-agent override for the website scraper.")
    LINKEDIN_AGENT_MODE: str = Field(default="", description="Per-agent override for the LinkedIn scraper.")
    SEARCH_AGENT_MODE: str = Field(default="", description="Per-agent override for the external/Google search agent.")
    COMPACTOR_MODE: str = Field(default="", description="Per-agent override for the profile compactor.")
    RFP_PARSER_MODE: str = Field(default="", description="Per-agent override for RFP PDF parsing.")
    RFP_RESPONSE_MODE_AI: str = Field(default="", description="Per-agent override for RFP response document generation.")
    BIDFORGE_MODE: str = Field(default="", description="Per-agent override for the BidForge-style pipeline.")

    BIDFORGE_STRICT_AI: bool = Field(
        default=True,
        description=(
            "When true, run_with_fallback() re-raises AI failures instead of silently "
            "degrading to the vague rule-based path."
        ),
    )

    # ------------------------------------------------------------------
    # JWT Authentication, Mailer, Zoom & Google Settings (Consolidated)
    # ------------------------------------------------------------------
    JWT_SECRET: str = Field(default="", description="JWT signing secret.")
    JWT_EXPIRES_DAYS: int = Field(
        default=7,
        validation_alias="JWT_EXPIRES_IN",
        description="Number of days a JWT is valid (mapped to JWT_EXPIRES_IN env key)."
    )

    @field_validator("JWT_EXPIRES_DAYS", mode="before")
    @classmethod
    def parse_jwt_expires_in(cls, v: Any) -> int:
        if isinstance(v, str):
            v_clean = v.strip().lower()
            if v_clean.endswith("d"):
                try:
                    return int(v_clean[:-1])
                except ValueError:
                    pass
            elif v_clean.endswith("h"):
                try:
                    hours = int(v_clean[:-1])
                    return max(1, hours // 24)
                except ValueError:
                    pass
            try:
                return int(v_clean)
            except ValueError:
                pass
        try:
            return int(v)
        except (ValueError, TypeError):
            return 7
    OTP_TTL_MINUTES: int = Field(default=10, description="OTP lifetime in minutes.")
    OTP_LENGTH: int = Field(default=6, description="Length of generated OTP.")
    DEBUG_OTP: bool = Field(default=False, description="Enable printing OTPs to console for development.")
    LOGIN_MAX_ATTEMPTS: int = Field(default=10, description="Max failed login attempts before 15-minute lockout.")
    SMTP_HOST: str = Field(default="smtp.gmail.com", description="SMTP server hostname.")
    SMTP_PORT: int = Field(default=465, description="SMTP server port.")
    SMTP_USER: str = Field(default="", description="SMTP account username/email.")
    SMTP_PASS: str = Field(default="", description="SMTP account password.")
    SMTP_FROM: str = Field(default="", description="Sender email address for outgoing mail.")

    @field_validator("SMTP_FROM", mode="before")
    @classmethod
    def parse_smtp_from(cls, v: Any) -> str:
        if isinstance(v, str):
            v_clean = v.strip().strip('"').strip("'")
            if "<" in v_clean and ">" in v_clean:
                import re
                match = re.search(r"<([^>]+)>", v_clean)
                if match:
                    return match.group(1).strip()
            return v_clean
        return str(v) if v else ""
    IMAP_HOST: str = Field(
        default="",
        description=(
            "IMAP server hostname used to poll for reply emails. "
            "Leave empty to auto-detect from SMTP_HOST (Gmail/Outlook/Yahoo supported); "
            "set explicitly for other providers (e.g. mail.yourdomain.com)."
        ),
    )
    IMAP_PORT: int = Field(default=993, description="IMAP server port (993 = IMAP over SSL, the standard for all major providers).")
    API_BASE_URL: str = Field(default="http://localhost:5050", description="API base URL used for tracking email opens and clicks.")
    CLIENT_URL: str = Field(default="http://localhost:5173", description="Frontend application client URL.")
    ZOOM_ACCOUNT_ID: str = Field(default="", description="Zoom account ID.")
    ZOOM_CLIENT_ID: str = Field(default="", description="Zoom client ID.")
    ZOOM_CLIENT_SECRET: str = Field(default="", description="Zoom client secret.")
    GOOGLE_CLIENT_ID: str = Field(default="", description="Google client ID.")
    GOOGLE_CLIENT_SECRET: str = Field(default="", description="Google client secret.")
    GOOGLE_REDIRECT_URI: str = Field(
        default="http://localhost:5050/api/integrations/google/callback",
        description="Google OAuth redirect URI.",
    )
    PORT: int = Field(default=5050, description="Port to run the API server on.")
    ENV: str = Field(default="dev", description="Environment mode: dev | prod.")
    CORS_ORIGINS: Union[list[str], str] = Field(
        default=[
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "http://localhost:3000",
            "http://127.0.0.1:3000",
        ],
        description="Allowed CORS origins for Frontend connectivity."
    )

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def parse_cors_origins(cls, v: Any) -> list[str]:
        if isinstance(v, str):
            v_clean = v.strip()
            if not v_clean:
                return ["*"]
            if v_clean.startswith("[") and v_clean.endswith("]"):
                import json
                try:
                    loaded = json.loads(v_clean)
                    if isinstance(loaded, list):
                        v = loaded
                except Exception:
                    pass
            if isinstance(v, str):
                origins = []
                for origin in v_clean.split(","):
                    o = origin.strip()
                    if not o:
                        continue
                    from urllib.parse import urlparse
                    parsed = urlparse(o)
                    if parsed.scheme and parsed.netloc:
                        origins.append(f"{parsed.scheme}://{parsed.netloc}")
                    else:
                        origins.append(o)
                return origins
        if isinstance(v, list):
            origins = []
            for origin in v:
                o = str(origin).strip()
                if not o:
                    continue
                from urllib.parse import urlparse
                parsed = urlparse(o)
                if parsed.scheme and parsed.netloc:
                    origins.append(f"{parsed.scheme}://{parsed.netloc}")
                else:
                    origins.append(o)
            return origins
        return [
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "http://localhost:3000",
            "http://127.0.0.1:3000",
        ]


    # ------------------------------------------------------------------
    # OCR (for scanned / image-only RFP PDFs that pypdf/PyMuPDF can't read)
    # ------------------------------------------------------------------
    OCR_ENABLED: bool = Field(
        default=True,
        description="If true, RFP PDF pages with no extractable text layer are rasterized and OCR'd.",
    )
    OCR_MIN_CHARS_PER_PAGE: int = Field(
        default=40,
        description="A page with fewer extracted characters than this is treated as scanned/image-only and sent to OCR.",
    )
    OCR_DPI: int = Field(
        default=300,
        description="DPI for rasterizing PDF pages for OCR (higher = better quality but slower).",
    )
    OLLAMA_TIMEOUT: int = Field(
        default=600,
        description="Timeout in seconds for Ollama API calls (set to 600s / 10 minutes for slow model generation like Gemma 4).",
    )
    CODESPACES: bool = Field(
        default=False,
        description="Set to True when running in GitHub Codespaces (enables 0.0.0.0 binding and adjusted paths).",
    )

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

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

    @property
    def mysql_uri(self) -> str:
        """
        Return the async MySQL connection URI.
        Prefers MYSQL_URI env var; otherwise builds from individual host/port/user/pass/db.
        """
        if self.MYSQL_URI:
            return self.MYSQL_URI
        if self.MYSQL_PASSWORD:
            return (
                f"mysql+asyncmy://{self.MYSQL_USER}:{self.MYSQL_PASSWORD}"
                f"@{self.MYSQL_HOST}:{self.MYSQL_PORT}/{self.MYSQL_DB}"
            )
        return (
            f"mysql+asyncmy://{self.MYSQL_USER}"
            f"@{self.MYSQL_HOST}:{self.MYSQL_PORT}/{self.MYSQL_DB}"
        )

    @property
    def mysql_uri_sync(self) -> str:
        """
        Return the synchronous MySQL connection URI (pymysql dialect).
        Used by background workers and cron jobs.
        """
        if self.MYSQL_URI_SYNC:
            return self.MYSQL_URI_SYNC
        uri = self.mysql_uri
        uri = uri.replace("mysql+asyncmy://", "mysql+pymysql://")
        uri = uri.replace("mysql+aiomysql://", "mysql+pymysql://")
        return uri


# Module-level singleton — import this everywhere
settings = AppSettings()
