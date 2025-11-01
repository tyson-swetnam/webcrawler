"""
SQLAlchemy database models for the AI News Crawler.

This module defines the database schema using SQLAlchemy ORM models.
Models include URLs, Articles, AI Analyses, Notifications, and Host Crawl State.
"""

from datetime import datetime
from sqlalchemy import (
    Column, BigInteger, Integer, SmallInteger, String, Text, Boolean,
    Float, Date, DateTime, CHAR, Interval, ARRAY, CheckConstraint,
    ForeignKey, UniqueConstraint
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship

Base = declarative_base()


class URL(Base):
    """
    URL tracking table with hash-based deduplication.

    Uses SHA-256 hashing for O(1) lookups and content change detection.
    """
    __tablename__ = 'urls'

    url_id = Column(BigInteger, primary_key=True, autoincrement=True)
    url = Column(Text, nullable=False, unique=True, index=True)
    url_hash = Column(CHAR(64), nullable=False, unique=True, index=True)
    normalized_url = Column(Text, nullable=False)
    hostname = Column(String(255), nullable=False, index=True)

    # Crawl tracking
    first_seen = Column(DateTime, nullable=False, default=datetime.utcnow)
    last_checked = Column(DateTime)
    status = Column(String(20), nullable=False, default='pending', index=True)
    http_status_code = Column(SmallInteger)

    # Content tracking for change detection
    content_hash = Column(CHAR(64), index=True)
    etag = Column(String(255))  # HTTP ETag for conditional requests

    # Retry logic
    retry_count = Column(SmallInteger, default=0)
    next_retry_at = Column(DateTime)
    permanent_fail = Column(Boolean, default=False)

    # Relationships
    articles = relationship("Article", back_populates="url")

    # Constraints
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'crawled', 'failed', 'redirect', 'excluded')",
            name='valid_status'
        ),
    )

    def __repr__(self):
        return f"<URL(url_id={self.url_id}, hostname='{self.hostname}', status='{self.status}')>"


class Article(Base):
    """
    Extracted article content with metadata and AI classification.

    Stores the parsed content from crawled URLs along with publication metadata
    and AI relevance classification.
    """
    __tablename__ = 'articles'

    article_id = Column(BigInteger, primary_key=True, autoincrement=True)
    url_id = Column(BigInteger, ForeignKey('urls.url_id'), nullable=False, index=True)

    # Extracted content
    title = Column(Text)
    author = Column(String(255))
    published_date = Column(Date, index=True)
    content = Column(Text)
    content_hash = Column(CHAR(64), nullable=False)
    summary = Column(Text)

    # Classification
    is_ai_related = Column(Boolean, default=False, index=True)
    ai_confidence_score = Column(Float)
    keywords = Column(ARRAY(Text))

    # Metadata
    university_name = Column(String(255))
    language = Column(CHAR(2), default='en')
    word_count = Column(Integer)
    metadata = Column(JSONB)  # Flexible metadata storage

    # Timestamps
    first_scraped = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    last_analyzed = Column(DateTime)

    # Relationships
    url = relationship("URL", back_populates="articles")
    ai_analyses = relationship("AIAnalysis", back_populates="article")

    # Constraints
    __table_args__ = (
        UniqueConstraint('url_id', 'content_hash', name='unique_url_content'),
    )

    def __repr__(self):
        return f"<Article(article_id={self.article_id}, title='{self.title[:50]}...')>"


class AIAnalysis(Base):
    """
    AI analysis results from multiple providers.

    Stores individual results from Claude, OpenAI, and Gemini along with
    consensus summary and relevance scoring.
    """
    __tablename__ = 'ai_analyses'

    analysis_id = Column(BigInteger, primary_key=True, autoincrement=True)
    article_id = Column(BigInteger, ForeignKey('articles.article_id'), nullable=False, index=True)

    # Claude API results
    claude_summary = Column(Text)
    claude_key_points = Column(ARRAY(Text))

    # OpenAI API results
    openai_summary = Column(Text)
    openai_category = Column(String(100))

    # Gemini API results
    gemini_summary = Column(Text)
    gemini_sentiment = Column(String(50))

    # Consensus and scoring
    consensus_summary = Column(Text)
    relevance_score = Column(Float)

    # Processing metadata
    analyzed_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    processing_time_ms = Column(Integer)

    # Relationships
    article = relationship("Article", back_populates="ai_analyses")

    def __repr__(self):
        return f"<AIAnalysis(analysis_id={self.analysis_id}, article_id={self.article_id})>"


class NotificationSent(Base):
    """
    Log of notifications sent via Slack and email.

    Tracks when notifications were sent, to which channels, and delivery status.
    """
    __tablename__ = 'notifications_sent'

    notification_id = Column(BigInteger, primary_key=True, autoincrement=True)
    notification_date = Column(Date, nullable=False, index=True)
    channel = Column(String(20), nullable=False)  # 'slack' or 'email'
    articles_count = Column(Integer, nullable=False)
    recipients = Column(ARRAY(Text))
    sent_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    status = Column(String(20), nullable=False)  # 'success', 'failed', 'partial'
    error_message = Column(Text)

    def __repr__(self):
        return f"<NotificationSent(notification_id={self.notification_id}, channel='{self.channel}', status='{self.status}')>"


class HostCrawlState(Base):
    """
    Per-domain crawl state for politeness and rate limiting.

    Tracks last crawl time, configured delays, and temporary blocks
    to ensure ethical crawling practices.
    """
    __tablename__ = 'host_crawl_state'

    hostname = Column(String(255), primary_key=True)
    last_crawl_time = Column(DateTime, nullable=False, default=datetime.utcnow)
    crawl_delay = Column(Interval, default='1 second')
    robots_txt_delay = Column(Interval)
    blocked_until = Column(DateTime)

    def __repr__(self):
        return f"<HostCrawlState(hostname='{self.hostname}')>"
