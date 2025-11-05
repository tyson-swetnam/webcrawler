"""
Type-safe configuration management using Pydantic Settings.

This module provides centralized configuration with environment variable loading,
validation, and type safety for all application settings.
"""

from pydantic import Field, field_validator, HttpUrl
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List
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

    # AI API Keys (SecretStr prevents logging)
    anthropic_api_key: str = Field(..., description="Anthropic Claude API key")
    openai_api_key: str = Field(..., description="OpenAI API key")

    # AI API Configuration
    claude_model: str = Field(
        default="claude-haiku-4-5-20251001",
        description="Claude Haiku model to use for primary analysis"
    )
    claude_haiku_model: str = Field(
        default="claude-haiku-4-5-20251001",
        description="Claude Haiku model to use for fast processing"
    )
    openai_model: str = Field(default="gpt-5-search-api-2025-10-14", description="OpenAI model to use")
    max_ai_tokens: int = Field(default=1024, description="Maximum tokens for AI responses")
    max_haiku_tokens: int = Field(default=512, description="Maximum tokens for Haiku responses")

    # Web crawling configuration
    max_concurrent_requests: int = Field(
        default=8,
        ge=1,
        le=50,
        description="Maximum concurrent HTTP requests"
    )
    crawl_delay: float = Field(
        default=1.0,
        ge=0.5,
        description="Delay between requests to same domain (seconds)"
    )
    user_agent: str = Field(
        default="AI-News-Crawler/1.0 (Research; +https://github.com/yourorg/ai-news-crawler)",
        description="User-Agent string for HTTP requests"
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

    # Notification configuration
    slack_webhook_url: str = Field(
        ...,
        description="Slack webhook URL for notifications"
    )
    email_from: str = Field(..., description="Email sender address")
    email_to: List[str] = Field(
        ...,
        description="List of email recipient addresses"
    )
    smtp_host: str = Field(default="smtp.gmail.com", description="SMTP server hostname")
    smtp_port: int = Field(default=465, description="SMTP server port")
    smtp_password: str = Field(..., description="SMTP password (use app password for Gmail)")
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
    min_article_length: int = Field(
        default=100,
        description="Minimum article length in characters"
    )
    max_article_age_days: int = Field(
        default=7,
        ge=1,
        le=30,
        description="Maximum age of articles to process (in days, default: 7 for recent news only)"
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
        default=True,
        description="Enable Slack notifications"
    )
    enable_email_notifications: bool = Field(
        default=True,
        description="Enable email notifications"
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

        Returns:
            List of file paths to load
        """
        paths = []

        # Map source types to file paths
        source_type_map = {
            "legacy": "crawler/config/universities.json",
            "r1": "crawler/config/r1_universities.json",
            "top_public": "crawler/config/top_public_universities.json",
            "top_universities": "crawler/config/top_universities.json",
            "peer_institutions": "crawler/config/peer_institutions.json",
            "meta_news": "crawler/config/meta_news_services.json",
            "major_facilities": "crawler/config/major_facilities.json"
        }

        # If 'all' is specified, load all university lists plus major facilities
        source_type = self.university_source_type.lower()
        if source_type == "all":
            paths.extend([
                "crawler/config/peer_institutions.json",   # Peer institutions (27)
                "crawler/config/r1_universities.json",     # R1 institutions (187)
                "crawler/config/major_facilities.json"     # Major research facilities (27)
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

            elif source_format == "university":
                # New university format with nested news structure
                # Schema v3.0.0: news_sources is an array of source objects
                # Legacy: news_sources.primary or news object
                news = {}

                if "news_sources" in source:
                    news_sources = source.get("news_sources", [])
                    if isinstance(news_sources, list) and news_sources:
                        # Schema v3.0.0: Find primary source in array
                        for ns in news_sources:
                            if ns.get("type") == "primary":
                                news = ns
                                break
                        # If no primary found, use first source
                        if not news:
                            news = news_sources[0]
                    elif isinstance(news_sources, dict):
                        # Legacy format: news_sources.primary
                        news = news_sources.get("primary", {})
                elif "news" in source:
                    # Legacy format: news object
                    news = source.get("news", {})

                # Determine which URL to use
                if self.prefer_ai_tag_urls and news.get("ai_tag_url"):
                    primary_url = news.get("ai_tag_url")
                    fallback_url = news.get("main_url") or news.get("url")
                else:
                    primary_url = news.get("main_url") or news.get("url")
                    fallback_url = news.get("ai_tag_url")

                # Use RSS feed if enabled and available
                news_url = primary_url
                rss_feed = None

                if self.use_rss_feeds and news.get("rss_feed"):
                    rss_feed = news.get("rss_feed")
                    # Prefer RSS over HTML crawling
                    if rss_feed and isinstance(rss_feed, str):
                        news_url = rss_feed

                location_obj = source.get("location", {})
                location = f"{location_obj.get('city', '')}, {location_obj.get('state', '')}".strip(", ")

                ai_research = source.get("ai_research", {})

                entry = {
                    "name": source.get("name"),
                    "abbreviation": source.get("abbreviation"),
                    "news_url": news_url or primary_url,
                    "ai_tag_url": news.get("ai_tag_url"),
                    "main_url": news.get("main_url") or news.get("url"),
                    "rss_feed": rss_feed,
                    "press_releases": news.get("press_releases"),
                    "location": location,
                    "focus_areas": ai_research.get("ai_focus_areas", []),
                    "source_type": "university",
                    "institution_type": source.get("classification", {}).get("institution_type"),
                    "media_relations": source.get("media_relations", {}),
                    "verified": news.get("verified", False)
                }

            elif source_format == "facility":
                # Major research facilities format
                # Schema v3.0.0: news_sources is an array of source objects
                news = {}

                if "news_sources" in source:
                    news_sources = source.get("news_sources", [])
                    if isinstance(news_sources, list) and news_sources:
                        # Schema v3.0.0: Find primary source in array
                        for ns in news_sources:
                            if ns.get("type") == "primary":
                                news = ns
                                break
                        # If no primary found, use first source
                        if not news:
                            news = news_sources[0]
                    elif isinstance(news_sources, dict):
                        # Legacy format: news_sources.primary
                        news = news_sources.get("primary", {})

                location_obj = source.get("location", {})
                location = f"{location_obj.get('city', '')}, {location_obj.get('state', '')}".strip(", ")

                entry = {
                    "name": source.get("name"),
                    "abbreviation": source.get("abbreviation"),
                    "news_url": news.get("url"),
                    "ai_tag_url": news.get("ai_tag_url"),
                    "rss_feed": None,
                    "location": location,
                    "focus_areas": source.get("research_focus", []),
                    "source_type": "facility",
                    "facility_type": source.get("facility_type"),
                    "affiliated_institution": source.get("affiliated_institution"),
                    "crawl_priority": news.get("crawl_priority", 100),
                    "verified": news.get("verified", False)
                }

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
            news_url = entry.get("news_url", "")
            is_verified = entry.get("verified", True)  # Default to True for legacy sources without verification field
            if news_url and "universityof.edu" not in news_url and is_verified:
                normalized.append(entry)

        return normalized

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
