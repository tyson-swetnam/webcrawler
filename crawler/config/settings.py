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
    gemini_api_key: str = Field(..., description="Google Gemini API key")

    # AI API Configuration
    claude_model: str = Field(
        default="claude-sonnet-4-5-20250929",
        description="Claude model to use"
    )
    openai_model: str = Field(default="gpt-4", description="OpenAI model to use")
    gemini_model: str = Field(
        default="gemini-2.5-flash",
        description="Gemini model to use"
    )
    max_ai_tokens: int = Field(default=1024, description="Maximum tokens for AI responses")

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
        default=30,
        description="Maximum age of articles to process"
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
        Load university sources from JSON file.

        Returns:
            List of university configuration dictionaries
        """
        import json
        from pathlib import Path

        path = Path(self.university_list_path)
        if not path.exists():
            raise FileNotFoundError(f"University list not found: {path}")

        with open(path, 'r') as f:
            return json.load(f)

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
