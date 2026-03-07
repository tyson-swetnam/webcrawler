# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

AI University News Crawler — a Python application that crawls 241+ US university and research facility news sites for AI-related content, analyzes articles via Claude and OpenAI APIs, and publishes a daily static website to GitHub Pages.

**Live site:** https://tyson-swetnam.github.io/webcrawler

## Running the Crawler

There is only ONE production entry point:

```bash
source venv/bin/activate && python -m crawler
```

This runs the complete pipeline:
1. Scrapy crawl of university news sites (in subprocess to avoid Twisted/asyncio conflict)
2. Content extraction via Trafilatura
3. Deduplication via SHA-256 URL/content hashing against PostgreSQL
4. Parallel AI analysis (Claude Haiku + OpenAI GPT-5) with consensus building
5. HTML report generation to both `output/` and `docs/` directories
6. Slack and email notifications

Debug a single university:
```bash
source venv/bin/activate && scrapy crawl university_news -a start_urls='["https://news.stanford.edu"]'
```

### Automated Execution

- **Systemd timer**: Runs daily at 06:00 MST via `scripts/run_crawler_and_commit.sh` (activates venv, crawls, commits `docs/` changes, pushes to `website` branch)
- **GitHub Actions**: `.github/workflows/daily-crawler.yml` runs at 15:00 UTC, uses ephemeral PostgreSQL, pushes to `website` branch
- Check timer: `systemctl status ai-news-crawler.timer`

## Development Setup

```bash
python3 -m venv venv && source venv/bin/activate && pip install -r requirements.txt
cp .env.example .env  # Edit with API keys and DATABASE_URL
```

### Code Quality

```bash
black crawler/       # Format
flake8 crawler/      # Lint
mypy crawler/        # Type check
```

### Testing

No formal test suite exists. Ad-hoc test scripts are in `scripts/`:
- `scripts/test_notifications.py` — test Slack/email delivery
- `scripts/test_html_generator.py` — test HTML generation
- `scripts/test_mcp_fetcher.py` — test MCP fetch fallback
- `scripts/test_api_keys.sh` — verify API key connectivity
- `scripts/test_database.sh` — verify DB connectivity

### Database

Tables are created by `Base.metadata.create_all()` in `DatabaseManager.create_tables()`. Alembic is configured but the `migrations/versions/` directory is empty. A raw SQL schema is available at `scripts/schema.sql`.

```bash
# Manual setup (alternative to scripts/setup_database.sh)
sudo -u postgres psql -c "CREATE DATABASE ai_news_crawler; CREATE USER crawler WITH PASSWORD 'pw'; GRANT ALL PRIVILEGES ON DATABASE ai_news_crawler TO crawler;"
```

## Architecture

### Pipeline Flow (`crawler/__main__.py`)

`cli()` → `asyncio.run(main())`:

1. **Crawl**: `run_crawler()` spawns a subprocess running `CrawlerProcess` with `UniversityNewsSpider` to avoid Twisted reactor conflicts with asyncio
2. **Retrieve**: Queries `articles` table for rows with `last_analyzed IS NULL` and recent `first_scraped`/`published_date`
3. **AI Analysis**: `MultiAIAnalyzer.batch_analyze()` fires three async API calls per article via `asyncio.gather()`, builds consensus
4. **Export**: `LocalExporter.export_all()` writes JSON/CSV/HTML/TXT to `output/`
5. **Website**: `HTMLReportGenerator` generates Drudge Report-style static site to both `output/` and `docs/`
6. **Notify**: `SlackNotifier` and `EmailNotifier` send daily reports

### Key Modules

| Module | Purpose |
|--------|---------|
| `crawler/__main__.py` | Entry point, pipeline orchestration |
| `crawler/config/settings.py` | Pydantic Settings, all config from `.env`. Global instance: `from crawler.config.settings import settings` |
| `crawler/spiders/university_spider.py` | Scrapy spider. Extracts content via Trafilatura `bare_extraction()`. Checks URLs against DB for dedup. Falls back to `MCPFetcher` on 403/404 |
| `crawler/ai/analyzer.py` | `MultiAIAnalyzer` — parallel Claude + OpenAI analysis. Consensus: prefers Claude summary, majority vote on `is_ai_related`, averages relevance scores |
| `crawler/db/models.py` | SQLAlchemy ORM: `URL`, `Article`, `AIAnalysis`, `NotificationSent`, `HostCrawlState` |
| `crawler/db/session.py` | `DatabaseManager` — connection pooling, `create_tables()`, session management |
| `crawler/extractors/content.py` | `ContentExtractor` (Trafilatura wrapper) + `DateExtractor` |
| `crawler/utils/html_generator.py` | `HTMLReportGenerator` — generates the static website with three-column layout |
| `crawler/utils/university_classifier.py` | `UniversityClassifier` — categorizes articles into Peer/R1/Facility columns |
| `crawler/utils/university_name_mapper.py` | Maps hostnames to canonical university names (uses `universities.json`) |
| `crawler/utils/local_exporter.py` | JSON/CSV/HTML/TXT export to `output/` |
| `crawler/utils/deduplication.py` | SHA-256 URL/content hashing. `BloomFilter` class exists but is unused; dedup is DB-backed |
| `crawler/notifiers/slack.py` | Slack Block Kit notifications (max 10 articles) |
| `crawler/notifiers/email.py` | SMTP HTML+text email via SSL or TLS |

### University Source Configuration

Sources are split across multiple JSON files in `crawler/config/`:
- `peer_institutions.json` (27 sources) — top-tier: MIT, Stanford, CMU, etc.
- `r1_universities.json` (187 sources) — Carnegie R1 universities
- `major_facilities.json` (10 sources) — HPC & research centers
- `national_laboratories.json` (54 sources) — national labs: Argonne, Los Alamos, NIST, etc.
- `global_institutions.json` (102 sources) — international institutions

`settings.university_source_type = "all"` loads all five. Sources use schema v3.0.0 with `news_sources` arrays. Only entries with `verified: true` are crawled. RSS feeds are preferred over HTML when `USE_RSS_FEEDS=True`.

### AI Models (Actual Defaults)

Actual defaults in `settings.py`:
- `claude_model`: `claude-sonnet-4-6` (primary analysis)
- `claude_haiku_model`: `claude-haiku-4-5-20251001` (fast validation)
- `openai_model`: `gpt-5-search-api-2025-10-14` (categorization)

All three run in parallel via `asyncio.gather()`. Confidence = providers_succeeded / 3. Claude responses use structured text format (SUMMARY:/KEY_POINTS:/RELEVANCE:/AI_RELATED:) parsed by `_parse_claude_response()`.

### Website Generation

`HTMLReportGenerator` produces a Drudge Report-style static site with:
- **Three-column layout**: Peer Institutions | R1 Institutions | Major Facilities
- Classification via `UniversityClassifier` fuzzy-matching against source JSON files (priority: Facility > Peer > R1)
- **Dual output**: writes to both `output/` (local) and `docs/` (GitHub Pages, committed to `website` branch)
- Pages: `index.html` (last 5 days), `archive/YYYY-MM-DD.html` (daily), `archive/index.html` (file-scan based)
- Styling: `Courier New` monospace, black/white/red (`#cc0000`), responsive (single column below 1024px)

### Database Tables

- **urls**: URL tracking, SHA-256 `url_hash`, crawl status, content change detection via `content_hash`
- **articles**: Extracted content, `is_ai_related` boolean, `ai_confidence_score`, `university_name`, JSONB `article_metadata`
- **ai_analyses**: Individual provider results (Claude, OpenAI, Gemini columns — Gemini unused), consensus summary
- **notifications_sent**: Delivery log per channel
- **host_crawl_state**: Per-domain crawl delays, `blocked_until`

Unique constraint on articles: `(url_id, content_hash)` enables detecting content updates at same URL.

## Output Directories

- `output/` — local output (gitignored): results JSON, CSV exports, HTML reports, daily text summaries
- `docs/` — GitHub Pages (committed to `website` branch): `index.html`, `how_it_works.html`, `archive/`

## Custom Agents

`.claude/agents/url-verifier.md` — validates URLs from university news sources before content extraction.

## Deployment

```bash
# Full deployment from scratch
sudo bash scripts/deploy.sh

# Manual systemd install
sudo cp deployment/*.service deployment/*.timer /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now ai-news-crawler.timer

# View logs
journalctl -u ai-news-crawler -f
```
