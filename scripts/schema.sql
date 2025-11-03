-- AI News Crawler Database Schema
-- PostgreSQL 15+ required
-- This schema supports hash-based deduplication with content fingerprinting

-- ============================================================================
-- EXTENSIONS
-- ============================================================================

-- Enable pgcrypto for advanced hashing functions (optional but recommended)
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- ============================================================================
-- TABLES
-- ============================================================================

-- URLs tracking table
-- Stores all discovered URLs with deduplication via SHA-256 hash
CREATE TABLE IF NOT EXISTS urls (
    url_id BIGSERIAL PRIMARY KEY,
    url TEXT NOT NULL UNIQUE,
    url_hash CHAR(64) NOT NULL UNIQUE,          -- SHA-256 for fast lookups
    normalized_url TEXT NOT NULL,
    hostname VARCHAR(255) NOT NULL,

    -- Crawl tracking
    first_seen TIMESTAMP NOT NULL DEFAULT NOW(),
    last_checked TIMESTAMP,
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    http_status_code SMALLINT,

    -- Content tracking
    content_hash CHAR(64),                      -- Detect content changes
    etag VARCHAR(255),                          -- HTTP ETag for conditional requests

    -- Retry logic
    retry_count SMALLINT DEFAULT 0,
    next_retry_at TIMESTAMP,
    permanent_fail BOOLEAN DEFAULT FALSE,

    CONSTRAINT valid_status CHECK (status IN
        ('pending', 'crawled', 'failed', 'redirect', 'excluded'))
);

-- Articles with extracted content
-- Stores parsed article content with AI classification
CREATE TABLE IF NOT EXISTS articles (
    article_id BIGSERIAL PRIMARY KEY,
    url_id BIGINT NOT NULL REFERENCES urls(url_id),

    -- Extracted content
    title TEXT,
    author VARCHAR(255),
    published_date DATE,
    content TEXT,
    content_hash CHAR(64) NOT NULL,
    summary TEXT,

    -- Classification
    is_ai_related BOOLEAN DEFAULT FALSE,
    ai_confidence_score FLOAT,
    keywords TEXT[],

    -- Metadata
    university_name VARCHAR(255),
    language CHAR(2) DEFAULT 'en',
    word_count INTEGER,
    article_metadata JSONB,

    -- Timestamps
    first_scraped TIMESTAMP NOT NULL DEFAULT NOW(),
    last_analyzed TIMESTAMP,

    CONSTRAINT unique_url_content UNIQUE(url_id, content_hash)
);

-- AI analysis results
-- Stores results from Claude, OpenAI, and Gemini APIs
CREATE TABLE IF NOT EXISTS ai_analyses (
    analysis_id BIGSERIAL PRIMARY KEY,
    article_id BIGINT NOT NULL REFERENCES articles(article_id),

    -- API results
    claude_summary TEXT,
    claude_key_points TEXT[],
    openai_summary TEXT,
    openai_category VARCHAR(100),
    gemini_summary TEXT,
    gemini_sentiment VARCHAR(50),

    -- Consensus
    consensus_summary TEXT,
    relevance_score FLOAT,

    analyzed_at TIMESTAMP NOT NULL DEFAULT NOW(),
    processing_time_ms INTEGER
);

-- Notification log
-- Tracks all sent notifications (Slack and email)
CREATE TABLE IF NOT EXISTS notifications_sent (
    notification_id BIGSERIAL PRIMARY KEY,
    notification_date DATE NOT NULL,
    channel VARCHAR(20) NOT NULL,              -- 'slack' or 'email'
    articles_count INTEGER NOT NULL,
    recipients TEXT[],
    sent_at TIMESTAMP NOT NULL DEFAULT NOW(),
    status VARCHAR(20) NOT NULL
);

-- Host crawl state for politeness
-- Tracks per-domain crawl delays and robots.txt compliance
CREATE TABLE IF NOT EXISTS host_crawl_state (
    hostname VARCHAR(255) PRIMARY KEY,
    last_crawl_time TIMESTAMP NOT NULL DEFAULT NOW(),
    crawl_delay INTERVAL DEFAULT '1 second',
    robots_txt_delay INTERVAL,
    blocked_until TIMESTAMP
);

-- ============================================================================
-- INDEXES
-- ============================================================================

-- URLs table indexes
CREATE INDEX IF NOT EXISTS idx_urls_hostname ON urls(hostname);
CREATE INDEX IF NOT EXISTS idx_urls_status ON urls(status);
CREATE INDEX IF NOT EXISTS idx_urls_content_hash ON urls(content_hash);
CREATE INDEX IF NOT EXISTS idx_urls_recent_crawled ON urls(last_checked DESC, status)
    WHERE status = 'crawled';

-- Articles table indexes
CREATE INDEX IF NOT EXISTS idx_articles_url_id ON articles(url_id);
CREATE INDEX IF NOT EXISTS idx_articles_published ON articles(published_date DESC);
CREATE INDEX IF NOT EXISTS idx_articles_first_scraped ON articles(first_scraped DESC);
CREATE INDEX IF NOT EXISTS idx_articles_ai_related ON articles(is_ai_related)
    WHERE is_ai_related = TRUE;
CREATE INDEX IF NOT EXISTS idx_articles_article_metadata ON articles USING GIN(article_metadata);

-- AI analyses table indexes
CREATE INDEX IF NOT EXISTS idx_ai_analyses_article_id ON ai_analyses(article_id);

-- ============================================================================
-- USEFUL QUERIES (COMMENTED EXAMPLES)
-- ============================================================================

-- Get new AI-related articles from last 24 hours:
-- SELECT a.title, a.published_date, a.summary, u.url, a.university_name
-- FROM articles a
-- JOIN urls u ON a.url_id = u.url_id
-- WHERE a.is_ai_related = TRUE
--   AND a.first_scraped >= NOW() - INTERVAL '24 hours'
-- ORDER BY a.first_scraped DESC;

-- Check if URL exists (O(1) with hash index):
-- SELECT url_id FROM urls WHERE url_hash = 'your_sha256_hash';

-- Get crawl statistics by university:
-- SELECT university_name, COUNT(*) as article_count
-- FROM articles
-- WHERE is_ai_related = TRUE
-- GROUP BY university_name
-- ORDER BY article_count DESC
-- LIMIT 20;

-- Get AI analysis success rate:
-- SELECT
--     COUNT(*) as total_analyses,
--     COUNT(claude_summary) as claude_success,
--     COUNT(openai_summary) as openai_success,
--     COUNT(gemini_summary) as gemini_success
-- FROM ai_analyses
-- WHERE analyzed_at >= NOW() - INTERVAL '7 days';
