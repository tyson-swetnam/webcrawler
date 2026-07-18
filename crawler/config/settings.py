"""
Type-safe configuration management using Pydantic Settings.

This module provides centralized configuration with environment variable loading,
validation, and type safety for all application settings.
"""

from pydantic import AliasChoices, Field, field_validator, model_validator, HttpUrl
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import ClassVar, List, Optional
from pathlib import Path


class Settings(BaseSettings):
    """
    Application configuration with type-safe settings.

    All settings can be overridden via environment variables.
    Secret values are handled securely with SecretStr type.
    """

    # Application settings
    app_name: str = Field(default="AI News Crawler", description="Application name")
    debug: bool = Field(default=False, description="Debug mode")
    log_level: str = Field(default="INFO", description="Logging level")

    # Database configuration
    database_url: str = Field(
        ...,
        description="PostgreSQL connection string",
        examples=["postgresql://crawler:password@localhost:5432/ai_news_crawler"]
    )
    database_pool_size: int = Field(default=10, description="Database connection pool size")
    redis_url: str = Field(
        default="redis://localhost:6379/0",
        description="Redis connection string for caching"
    )

    # AI analysis via Claude Code CLI (Claude Max subscription auth).
    # Credentials come from the CLAUDE_CODE_OAUTH_TOKEN environment variable
    # (create once with `claude setup-token`); no API keys are required.
    claude_code_model: str = Field(
        default="sonnet",
        description="Model alias or full id passed to the Claude Code CLI (--model)"
    )
    ai_articles_per_prompt: int = Field(
        default=15,
        ge=1,
        le=25,
        description="Articles batched into one Claude message (quota conservation)"
    )
    ai_max_content_chars: int = Field(
        default=1500,
        description="Per-article content truncation inside batched prompts"
    )
    claude_cli_timeout: int = Field(
        default=300,
        description="Timeout in seconds for one Claude CLI invocation"
    )
    ai_message_budget: int = Field(
        default=400,
        description="Soft cap on subscription messages per run; analysis resumes next run"
    )
    max_pipeline_minutes: int = Field(
        default=75,
        ge=0,
        description=(
            "Wall-clock budget for the crawl+analysis phases (0 = unlimited). "
            "Analysis stops at the deadline so export and website publishing "
            "still happen inside the CI step timeout; leftovers resume next run."
        )
    )
    analyze_only: bool = Field(
        default=False,
        description=(
            "Skip crawling entirely and only analyze the stored backlog "
            "(used by the backlog-processor workflow). Env: ANALYZE_ONLY"
        )
    )

    # Web crawling configuration
    max_concurrent_requests: int = Field(
        default=24,
        ge=1,
        le=50,
        description="Maximum concurrent HTTP requests"
    )
    crawl_delay: float = Field(
        default=0.5,
        ge=0.25,
        description="Delay between requests to same domain (seconds)"
    )
    user_agent: str = Field(
        default=(
            "AIUniversityNewsBot/2.0 "
            "(+https://tyson-swetnam.github.io/webcrawler; mailto:tswetnam@arizona.edu)"
        ),
        description="Honest, identifiable User-Agent (site + contact) for HTTP requests"
    )
    request_timeout: int = Field(
        default=30,
        description="HTTP request timeout in seconds"
    )

    # University sources configuration
    university_list_path: str = Field(
        default="crawler/config/universities.json",
        description="Path to university sources JSON file"
    )
    university_source_type: str = Field(
        default="all",
        description="Type of university source: legacy, r1, top_public, top_universities, meta_news, or 'all' to use all lists"
    )
    prefer_ai_tag_urls: bool = Field(
        default=True,
        description="Prefer AI-specific tag URLs over general news URLs when available"
    )
    include_meta_news: bool = Field(
        default=False,
        description="Include meta news services (Chronicle, Inside Higher Ed, etc.) in crawling"
    )
    use_rss_feeds: bool = Field(
        default=True,
        description="Prefer RSS feeds over HTML crawling when available"
    )
    crawler_source_files: str = Field(
        default="",
        description="Comma-separated list of source JSON file paths (overrides university_source_type when set)"
    )

    # Notification configuration (all optional — validated only when the
    # matching enable_* feature flag is on)
    slack_webhook_url: Optional[str] = Field(
        default=None,
        description="Slack webhook URL for notifications"
    )
    email_from: Optional[str] = Field(default=None, description="Email sender address")
    email_to: List[str] = Field(
        default_factory=list,
        description="List of email recipient addresses"
    )
    smtp_host: str = Field(default="smtp.gmail.com", description="SMTP server hostname")
    smtp_port: int = Field(default=465, description="SMTP server port")
    smtp_password: Optional[str] = Field(default=None, description="SMTP password (use app password for Gmail)")
    smtp_use_ssl: bool = Field(default=True, description="Use SSL for SMTP connection")

    # Scheduling configuration
    run_daily_at: str = Field(
        default="00:00",
        description="Daily run time in HH:MM format (UTC)"
    )
    lookback_days: int = Field(
        default=1,
        ge=1,
        le=7,
        description="Number of days to look back for new articles"
    )

    # Content filtering
    min_article_words: int = Field(
        default=100,
        validation_alias=AliasChoices("MIN_ARTICLE_WORDS", "MIN_ARTICLE_LENGTH"),
        description="Minimum article length in words (MIN_ARTICLE_LENGTH kept as env alias)"
    )
    max_article_age_days: int = Field(
        default=5,
        ge=1,
        le=400,
        description=(
            "Maximum age of articles to process (in days, default: 5 for recent "
            "news only). Daily CI runs use 30; the archive-backfill workflow "
            "widens this to reach articles published during crawler outages."
        )
    )

    # Logging configuration
    log_file_path: str = Field(
        default="/var/log/ai-news-crawler/crawler.log",
        description="Log file path"
    )
    log_max_bytes: int = Field(
        default=10485760,
        description="Maximum log file size (10MB)"
    )
    log_backup_count: int = Field(
        default=5,
        description="Number of log backups to keep"
    )

    # Feature flags
    enable_ai_analysis: bool = Field(
        default=True,
        description="Enable AI analysis of articles"
    )
    enable_slack_notifications: bool = Field(
        default=False,
        description="Enable Slack notifications (requires SLACK_WEBHOOK_URL)"
    )
    enable_email_notifications: bool = Field(
        default=False,
        description="Enable email notifications (requires EMAIL_FROM/EMAIL_TO/SMTP_PASSWORD)"
    )

    # Local output configuration
    local_output_dir: str = Field(
        default="./output",
        description="Directory for local file outputs"
    )
    save_results_to_file: bool = Field(
        default=True,
        description="Save results to local files"
    )
    export_json: bool = Field(
        default=True,
        description="Export results as JSON"
    )
    export_csv: bool = Field(
        default=True,
        description="Export results as CSV"
    )
    export_html: bool = Field(
        default=True,
        description="Export results as HTML report"
    )
    export_text_summary: bool = Field(
        default=True,
        description="Export text summary"
    )

    # Performance tuning
    max_articles_per_run: int = Field(
        default=1000,
        description="Maximum articles to process per run"
    )
    ai_analysis_batch_size: int = Field(
        default=5,
        description="Number of concurrent AI analysis requests"
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )

    @field_validator('email_to', mode='before')
    @classmethod
    def parse_email_list(cls, v):
        """Parse email list from comma-separated string or JSON array."""
        if isinstance(v, str):
            # Handle comma-separated string
            if v.startswith('['):
                # JSON array format
                import json
                return json.loads(v)
            else:
                # Comma-separated format
                return [email.strip() for email in v.split(',')]
        return v

    @model_validator(mode='after')
    def validate_notification_config(self):
        """Require notification credentials only when the feature is enabled."""
        if self.enable_slack_notifications and not self.slack_webhook_url:
            raise ValueError(
                "ENABLE_SLACK_NOTIFICATIONS=true requires SLACK_WEBHOOK_URL "
                "(or set ENABLE_SLACK_NOTIFICATIONS=false)"
            )
        if self.enable_email_notifications and not (
            self.email_from and self.email_to and self.smtp_password
        ):
            raise ValueError(
                "ENABLE_EMAIL_NOTIFICATIONS=true requires EMAIL_FROM, EMAIL_TO and "
                "SMTP_PASSWORD (or set ENABLE_EMAIL_NOTIFICATIONS=false)"
            )
        return self

    @field_validator('run_daily_at')
    @classmethod
    def validate_time_format(cls, v):
        """Validate time is in HH:MM format."""
        try:
            hours, minutes = v.split(':')
            hours_int = int(hours)
            minutes_int = int(minutes)
            if not (0 <= hours_int < 24 and 0 <= minutes_int < 60):
                raise ValueError
            return v
        except (ValueError, AttributeError):
            raise ValueError(f"Invalid time format: {v}. Expected HH:MM")

    def get_university_sources(self) -> List[dict]:
        """
        Load university sources from JSON file(s).

        Supports both legacy format and new comprehensive format.
        Can combine universities with meta news services.

        Returns:
            List of university/source configuration dictionaries with standardized fields
        """
        import json
        from pathlib import Path

        sources = []

        # Determine which file(s) to load
        source_files = self._get_source_file_paths()

        for file_path in source_files:
            path = Path(file_path)
            if not path.exists():
                import logging
                logger = logging.getLogger(__name__)
                logger.warning(f"Source file not found: {path}, skipping")
                continue

            with open(path, 'r') as f:
                data = json.load(f)

            # Extract universities/sources based on file structure
            if isinstance(data, list):
                # Legacy format: direct array
                sources.extend(self._normalize_sources(data, "legacy"))
            elif isinstance(data, dict):
                if "universities" in data:
                    # New university format
                    sources.extend(self._normalize_sources(data["universities"], "university"))
                elif "facilities" in data:
                    # Major facilities format
                    sources.extend(self._normalize_sources(data["facilities"], "facility"))
                elif "news_services" in data:
                    # Meta news services format
                    if self.include_meta_news:
                        sources.extend(self._normalize_sources(data["news_services"], "meta_news"))
                else:
                    import logging
                    logger = logging.getLogger(__name__)
                    logger.warning(f"Unknown JSON structure in {path}")

        return sources

    def _get_source_file_paths(self) -> List[str]:
        """
        Get list of source file paths based on configuration.

        If CRAWLER_SOURCE_FILES env var is set, uses those paths exclusively.
        Otherwise falls back to university_source_type logic.

        Returns:
            List of file paths to load
        """
        # If crawler_source_files is set (e.g. by parallel subprocess), use it directly
        if self.crawler_source_files:
            return [p.strip() for p in self.crawler_source_files.split(",") if p.strip()]

        paths = []

        # Map source types to file paths
        source_type_map = {
            "legacy": "crawler/config/universities.json",
            "r1": "crawler/config/r1_universities.json",
            "top_public": "crawler/config/top_public_universities.json",
            "top_universities": "crawler/config/top_universities.json",
            "peer_institutions": "crawler/config/peer_institutions.json",
            "meta_news": "crawler/config/meta_news_services.json",
            "major_facilities": "crawler/config/major_facilities.json",
            "national_laboratories": "crawler/config/national_laboratories.json",
            "global_institutions": "crawler/config/global_institutions.json"
        }

        # If 'all' is specified, load all university lists plus facilities and labs
        source_type = self.university_source_type.lower()
        if source_type == "all":
            paths.extend([
                "crawler/config/peer_institutions.json",          # Peer institutions (27)
                "crawler/config/r1_universities.json",            # R1 institutions (187)
                "crawler/config/major_facilities.json",           # HPC & Research Centers (10)
                "crawler/config/national_laboratories.json",      # National Laboratories (54)
                "crawler/config/global_institutions.json"         # Global Institutions (102)
            ])
        # If custom path is set and different from default, use it
        elif self.university_list_path != "crawler/config/universities.json":
            paths.append(self.university_list_path)
        else:
            # Use source type to determine file
            if source_type in source_type_map:
                paths.append(source_type_map[source_type])
            else:
                paths.append(self.university_list_path)

        # Add meta news if enabled
        if self.include_meta_news and source_type_map["meta_news"] not in paths:
            paths.append(source_type_map["meta_news"])

        return paths

    def _normalize_sources(self, sources: List[dict], source_format: str) -> List[dict]:
        """
        Normalize source entries to a standard format.

        Args:
            sources: List of source dictionaries
            source_format: Format type ("legacy", "university", "meta_news")

        Returns:
            List of normalized source dictionaries
        """
        normalized = []

        for source in sources:
            entry = {}

            if source_format == "legacy":
                # Legacy format: {name, news_url, location, focus_areas}
                entry = {
                    "name": source.get("name"),
                    "news_url": source.get("news_url"),
                    "ai_tag_url": None,
                    "rss_feed": None,
                    "location": source.get("location"),
                    "focus_areas": source.get("focus_areas", []),
                    "source_type": "university"
                }

            elif source_format in ("university", "facility"):
                # Schema v3.0.0: news_sources is an ARRAY of source objects
                # (primary, secondary, ai_tag). Emit one crawlable entry per
                # verified source instead of only the primary — this is where
                # most of the site's discovery coverage comes from.
                normalized.extend(self._institution_entries(source, source_format))
                continue

            elif source_format == "meta_news":
                # Meta news services format
                rss = source.get("rss_feeds", {})

                # Determine URL to use
                news_url = source.get("url")
                if self.use_rss_feeds:
                    if isinstance(rss, dict) and rss.get("available") and rss.get("main_feed"):
                        news_url = rss.get("main_feed")
                    elif isinstance(rss, str):
                        news_url = rss

                entry = {
                    "name": source.get("name"),
                    "abbreviation": source.get("abbreviation"),
                    "news_url": news_url,
                    "ai_tag_url": source.get("higher_ed_section"),
                    "rss_feed": rss.get("main_feed") if isinstance(rss, dict) else rss,
                    "location": source.get("coverage", ""),
                    "focus_areas": source.get("focus_areas", []),
                    "source_type": "meta_news",
                    "description": source.get("description")
                }

            # Only add if we have a valid URL, not a placeholder domain, and is verified
            if self._is_valid_entry(entry):
                normalized.append(entry)

        return normalized

    @staticmethod
    def _is_valid_entry(entry: dict) -> bool:
        """Entry has a real (non-placeholder) URL and is verified."""
        news_url = entry.get("news_url") or ""
        # Default to True for legacy sources without verification field
        is_verified = entry.get("verified", True)
        return bool(
            news_url
            and "universityof.edu" not in news_url
            and "universityat.edu" not in news_url
            and "theuniversity.edu" not in news_url
            and is_verified
        )

    # Max crawlable entries emitted per institution (primary + ai_tag + secondary)
    MAX_SOURCES_PER_INSTITUTION: ClassVar[int] = 3

    def _institution_entries(self, source: dict, source_format: str) -> List[dict]:
        """Build one normalized entry per verified news_sources element.

        Handles schema v3.0.0 arrays plus the legacy `news_sources.primary`
        dict and `news` object shapes. Entries are ordered primary → ai_tag →
        secondary, deduplicated by resolved URL, and capped per institution.
        """
        news_sources = source.get("news_sources")
        ns_list: List[dict] = []
        if isinstance(news_sources, list):
            ns_list = [ns for ns in news_sources if isinstance(ns, dict)]
        elif isinstance(news_sources, dict):
            primary = news_sources.get("primary")
            if isinstance(primary, dict):
                ns_list = [primary]
        elif isinstance(source.get("news"), dict):
            ns_list = [source["news"]]

        role_rank = {"primary": 0, "ai_tag": 1, "secondary": 2}
        ns_list.sort(key=lambda ns: role_rank.get(ns.get("type"), 3))

        location_obj = source.get("location", {})
        location = f"{location_obj.get('city', '')}, {location_obj.get('state', '')}".strip(", ")

        if source_format == "university":
            ai_research = source.get("ai_research", {})
            base = {
                "name": source.get("name"),
                "abbreviation": source.get("abbreviation"),
                "location": location,
                "focus_areas": ai_research.get("ai_focus_areas", []),
                "source_type": "university",
                "institution_type": source.get("classification", {}).get("institution_type"),
                "media_relations": source.get("media_relations", {}),
            }
        else:
            base = {
                "name": source.get("name"),
                "abbreviation": source.get("abbreviation"),
                "location": location,
                "focus_areas": source.get("research_focus", []),
                "source_type": "facility",
                "facility_type": source.get("facility_type"),
                "affiliated_institution": source.get("affiliated_institution"),
            }

        entries: List[dict] = []
        seen_urls: set = set()

        for ns in ns_list:
            main_url = ns.get("main_url") or ns.get("url")

            # Determine which URL to use
            if self.prefer_ai_tag_urls and ns.get("ai_tag_url"):
                primary_url = ns.get("ai_tag_url")
            else:
                primary_url = main_url

            # Prefer RSS over HTML crawling when enabled and available
            news_url = primary_url
            rss_feed = ns.get("rss_feed") if self.use_rss_feeds else None
            if rss_feed and isinstance(rss_feed, str):
                news_url = rss_feed

            entry = {
                **base,
                "news_url": news_url or primary_url,
                "ai_tag_url": ns.get("ai_tag_url"),
                "main_url": main_url,
                "rss_feed": rss_feed,
                "press_releases": ns.get("press_releases"),
                "sitemaps": ns.get("sitemaps") or source.get("sitemaps") or [],
                "source_role": ns.get("type", "primary"),
                "crawl_priority": ns.get("crawl_priority", 100),
                "verified": ns.get("verified", False),
            }

            if not self._is_valid_entry(entry):
                continue
            if entry["news_url"] in seen_urls:
                continue
            seen_urls.add(entry["news_url"])
            entries.append(entry)
            if len(entries) >= self.MAX_SOURCES_PER_INSTITUTION:
                break

        return entries

    @property
    def is_production(self) -> bool:
        """Check if running in production mode."""
        return not self.debug

    @property
    def database_echo(self) -> bool:
        """Whether to echo SQL statements."""
        return self.debug


# Global settings instance
settings = Settings()
