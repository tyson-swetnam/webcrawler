# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is an **AI University News Crawler** - a production-grade Python application that crawls US university news sites for AI-related content, leverages multiple AI APIs for analysis, and delivers intelligent summaries via Slack and email. The system is designed as a standalone Linux application with daily automated execution.

## Architecture

The system follows a **producer-consumer pattern** with 6 distinct phases:

1. **Discovery & Crawling**: Scrapy-based crawler identifies new articles from university press releases
2. **Content Extraction**: Trafilatura extracts structured content with 95%+ accuracy
3. **Deduplication**: PostgreSQL + Bloom filters identify truly new content
4. **AI Analysis**: Parallel calls to Claude (Sonnet-4-5 and Haiku) and OpenAI (GPT-4/GPT-5) for deep research
5. **Reporting**: Generate summaries and deliver via Slack webhooks and SMTP email
6. **Persistence**: Store results, update tracking database, log all operations

### Technology Stack

- **Core**: Python 3.11+ with Scrapy 2.11+
- **Content Extraction**: Trafilatura 2.0+ with htmldate
- **Database**: PostgreSQL 15+ for metadata/tracking, Redis 7+ for URL frontier
- **AI APIs**: Anthropic Claude (Sonnet-4-5 and Haiku), OpenAI GPT-4/GPT-5
- **Scheduling**: Systemd timers (preferred) or cron
- **Notifications**: Slack webhooks + Python smtplib
- **Deployment**: Systemd service with virtual environment isolation

## Project Structure

```
ai-news-crawler/
├── crawler/                     # Main application package
│   ├── __main__.py              # Entry point: python -m crawler
│   ├── config/
│   │   ├── settings.py          # Pydantic configuration
│   │   ├── logging.yaml         # Logging configuration
│   │   └── universities.json    # University source list
│   ├── spiders/
│   │   ├── university_spider.py # Main Scrapy spider
│   │   └── discovery_spider.py  # New source discovery
│   ├── extractors/
│   │   ├── content.py           # Trafilatura wrapper
│   │   └── metadata.py          # Date/author extraction
│   ├── db/
│   │   ├── models.py            # SQLAlchemy models
│   │   ├── session.py           # Database connection
│   │   └── migrations/          # Alembic migrations
│   ├── ai/
│   │   └── analyzer.py          # Multi-API orchestration (Claude + OpenAI)
│   ├── notifiers/
│   │   ├── slack.py             # Slack webhook integration
│   │   └── email.py             # SMTP email sender
│   └── utils/
│       ├── deduplication.py     # Bloom filter + hashing
│       ├── rate_limiter.py      # Politeness controls
│       └── report_generator.py  # Summary formatting
├── tests/
│   ├── unit/
│   └── integration/
├── scripts/
│   ├── deploy.sh                # Deployment automation
│   ├── backup.sh                # Database backup
│   ├── discover_universities.py # Initial source discovery
│   └── test_notifications.py    # Test Slack/email
├── deployment/
│   ├── ai-news-crawler.service  # Systemd service
│   └── ai-news-crawler.timer    # Systemd timer
└── requirements.txt
```

## Database Schema

### Core Tables

- **urls**: URL tracking with hash-based deduplication (SHA-256 for O(1) lookups)
- **articles**: Extracted content with AI classification
- **ai_analyses**: Results from Claude (Sonnet + Haiku) and OpenAI APIs with consensus summary
- **notifications_sent**: Notification delivery log
- **host_crawl_state**: Per-domain politeness tracking

### Key Design Decisions

- Hash-based deduplication using SHA-256 for both URL and content fingerprinting
- Content hash stored separately from URL hash to detect article updates
- PostgreSQL indexes optimized for common queries (recent articles, AI-related content)
- JSONB metadata field for flexible schema evolution

## Development Commands

### Environment Setup

```bash
# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Copy and configure environment
cp .env.example .env
# Edit .env with your API keys and credentials
```

### Database Setup

```bash
# Setup PostgreSQL database (run as postgres user)
sudo -u postgres psql
CREATE DATABASE ai_news_crawler;
CREATE USER crawler WITH PASSWORD 'secure_password';
GRANT ALL PRIVILEGES ON DATABASE ai_news_crawler TO crawler;
\q

# Run migrations
alembic upgrade head
```

### Running the Crawler

**IMPORTANT:** There is only ONE production crawler entry point: `python -m crawler`

The crawler MUST be run with the virtual environment activated:

```bash
# Activate virtual environment and run the full pipeline (production command)
source venv/bin/activate && python -m crawler
```

This command runs the complete 6-phase pipeline:
1. Crawl university news sites (Scrapy)
2. Extract and deduplicate content
3. Analyze with AI APIs (Claude Sonnet-4-5, Claude Haiku, OpenAI GPT-4/GPT-5)
4. Generate HTML reports (Drudge Report-style website)
5. Send notifications (Slack + Email)
6. Store results in database

```bash
# Test single university crawl (Scrapy only - for debugging)
source venv/bin/activate && scrapy crawl university_news -a start_urls='["https://news.stanford.edu"]'
```

**Automated Daily Execution:**

The crawler is configured to run automatically via systemd timer every day at 06:00 MST. The systemd service calls `/home/tswetnam/github/webcrawler/scripts/run_crawler_and_commit.sh`, which:
1. Activates the virtual environment
2. Runs the crawler
3. Commits any changes to the `docs/` directory
4. Pushes to the `website` branch on GitHub

To check the systemd timer status:
```bash
systemctl status ai-news-crawler.timer
systemctl list-timers --all | grep ai-news-crawler
```

### Testing

```bash
# Run all tests
pytest

# Run unit tests only
pytest tests/unit/

# Run integration tests
pytest tests/integration/

# Test notifications (without actual crawling)
python scripts/test_notifications.py

# Test specific component
pytest tests/unit/test_ai_clients.py -v
```

### Deployment

```bash
# Automated deployment (recommended)
sudo bash scripts/deploy.sh

# Manual systemd service installation
sudo cp deployment/*.service /etc/systemd/system/
sudo cp deployment/*.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable ai-news-crawler.timer
sudo systemctl start ai-news-crawler.timer

# Check service status
systemctl status ai-news-crawler.timer
systemctl list-timers --all

# Manual trigger
sudo systemctl start ai-news-crawler.service

# View logs
journalctl -u ai-news-crawler -f
```

### Database Operations

```bash
# Create new migration
alembic revision --autogenerate -m "description"

# Apply migration
alembic upgrade head

# Rollback migration
alembic downgrade -1

# Backup database
bash scripts/backup.sh
```

### Health Monitoring

```bash
# Run health check
python scripts/health_check.py

# View recent crawl statistics (PostgreSQL query)
psql ai_news_crawler -c "
  SELECT COUNT(*), DATE(first_scraped)
  FROM articles
  WHERE is_ai_related = TRUE
  GROUP BY DATE(first_scraped)
  ORDER BY DATE(first_scraped) DESC
  LIMIT 7;
"
```

## Code Architecture Principles

### Configuration Management

- Use **Pydantic Settings** for type-safe configuration with validation
- All secrets loaded from environment variables (never commit .env files)
- Configuration class located in `crawler/config/settings.py`
- Global settings instance: `from crawler.config.settings import settings`

### Web Crawling Ethics

- **Always respect robots.txt** (Scrapy setting: `ROBOTSTXT_OBEY = True`)
- Implement per-domain rate limiting (default: 1 request/second)
- Use descriptive User-Agent string with contact information
- Store crawl delays in database (`host_crawl_state` table)
- Implement exponential backoff for failed requests

### AI API Integration

- Use **async/await** for parallel API calls to Claude (Sonnet + Haiku) and OpenAI
- Implement graceful degradation (system works if 1-2 APIs fail)
- Claude Sonnet-4-5 is the primary/highest-quality API
- Claude Haiku provides fast, cost-effective validation
- OpenAI GPT-4/GPT-5 provides categorization and additional summaries
- Apply rate limiting and token limits to control costs
- Store all API responses in `ai_analyses` table for auditing

### Error Handling

- Use structured JSON logging (pythonjsonlogger)
- Log to both console and rotating file handler
- All database operations in try/except with rollback
- Network requests use retry logic with exponential backoff
- Notification failures should log but not crash the pipeline

### Database Patterns

- Use SQLAlchemy ORM with type hints
- All queries use prepared statements (no SQL injection risk)
- Use hash indexes for O(1) URL lookups
- Implement connection pooling (default: 10 connections)
- Use database transactions for multi-table operations

### Testing Standards

- Unit tests for all parsing and extraction logic
- Integration tests for full crawl workflow
- Mock external APIs in tests (don't hit real endpoints)
- Test edge cases: empty content, malformed HTML, encoding issues
- Use pytest fixtures for database setup/teardown

## Critical Implementation Details

### Content Deduplication Strategy

The system uses **two-level hashing**:
1. **URL hash** (SHA-256): Check if URL has been seen before
2. **Content hash** (SHA-256): Detect if article content changed

This allows re-crawling URLs while detecting unchanged content.

### Multi-AI Consensus Building

Results from all three AI providers are collected, but:
- Claude Sonnet's summary is preferred (highest quality)
- Claude Haiku provides fast validation of AI-relevance
- OpenAI provides categorization and backup summaries
- Confidence score based on how many providers succeeded (0.33, 0.67, or 1.0)
- All individual responses stored for future re-analysis

### Politeness Implementation

Per-domain crawl delays stored in `host_crawl_state` table:
- Default: 1 second between requests
- Respects `Crawl-delay` from robots.txt
- Implements `blocked_until` for temporary bans
- Uses `DomainRateLimiter` class for enforcement

### Notification Format

- **Slack**: Rich blocks format with clickable links, max 10 articles shown
- **Email**: HTML format with responsive design, all articles included
- Both channels receive identical content summaries
- Delivery failures logged to `notifications_sent` table

## Security Considerations

- Never commit `.env` files (in `.gitignore`)
- Use app passwords for Gmail SMTP (not account password)
- Run systemd service as non-root user (`crawler`)
- Set strict file permissions: `chmod 600 .env`
- Database connections use SSL in production
- API keys stored as `SecretStr` type in Pydantic settings
- Validate all URLs before crawling (prevent SSRF attacks)

## Cost Optimization

Estimated monthly costs (100 articles/day):
- Claude Sonnet-4-5: ~$9/month (primary analysis)
- Claude Haiku: ~$0.50/month (fast validation)
- OpenAI GPT-4/GPT-5: ~$27/month (categorization)
- **Total: ~$36.50/month**

Optimization strategies:
1. Use Claude Haiku for initial AI-relevance filtering (fast and cheap)
2. Only send confirmed AI articles to expensive models
3. Set max_tokens limits on all API calls
4. Cache AI summaries to avoid reprocessing

## Custom Agents

This repository includes specialized Claude Code agents in `.claude/agents/`:

- **python-web-crawler-architect**: Expert guidance on web crawling, schema.org extraction, and data pipeline architecture
- **architect-agent**: Orchestrates complex development workflows and coordinates multiple specialized agents

These agents are automatically available when working in this codebase and will proactively assist with relevant tasks.
