# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

AI University News Crawler — a Python application that crawls 380+ university, national-laboratory, and research-facility news sites for AI-related content, analyzes articles with Claude (via the Claude Code CLI, authenticated with a Claude Max subscription — no API keys), and publishes a daily static website to GitHub Pages.

**Live site:** https://tyson-swetnam.github.io/webcrawler

## Running the Crawler

There is only ONE production entry point:

```bash
source venv/bin/activate && python -m crawler
```

This runs the complete pipeline:
1. Scrapy crawl of university news sites (three parallel subprocess groups to avoid Twisted/asyncio conflict): front pages + RSS feeds + sitemaps (config, robots.txt, /sitemap.xml)
2. Content extraction via Trafilatura, with htmldate + discovery-channel date fallbacks (undated articles are excluded)
3. Deduplication via SHA-256 URL/content hashing against PostgreSQL
4. Batched Claude analysis via the Claude Code CLI (~15 articles/prompt, structured JSON output)
5. HTML report generation to both `output/` and `docs/` directories
6. Optional Slack/email notifications (disabled by default)

Debug a single university:
```bash
source venv/bin/activate && scrapy crawl university_news -a start_urls='["https://news.stanford.edu"]'
```

### AI Backend (Claude Max subscription)

Analysis calls go through `claude -p --output-format json --json-schema` (headless Claude Code CLI). Auth is the `CLAUDE_CODE_OAUTH_TOKEN` env var created with `claude setup-token` (~1-year lifetime). There are NO `ANTHROPIC_API_KEY`/`OPENAI_API_KEY` settings anymore.

- `crawler/ai/claude_cli.py` — low-level runner; raises `ClaudeQuotaExhausted` when the subscription window is used up (hard stop, not a 429)
- `crawler/ai/claude_code_analyzer.py` — batches `AI_ARTICLES_PER_PROMPT` (15) articles per message; failed/skipped articles keep `last_analyzed = NULL` so the next run resumes them
- `AI_MESSAGE_BUDGET` (400) soft-caps subscription messages per run
- Never pass `--bare` to the CLI — it skips OAuth token reads

### Automated Execution

- **GitHub Actions is the production scheduler**: `.github/workflows/daily-crawler.yml` runs at 15:00 UTC, uses ephemeral PostgreSQL (hydrated from `docs/data/articles.parquet` on the `website` branch), installs a pinned Claude Code CLI, and pushes to the `website` branch with rebase+retry. Requires the `CLAUDE_CODE_OAUTH_TOKEN` repository secret.
- The systemd timer / cron scripts under `deployment/` and `scripts/` are **deprecated** (they race the workflow on the `website` branch): `sudo systemctl disable --now ai-news-crawler.timer`

## Development Setup

```bash
python3 -m venv venv && source venv/bin/activate && pip install -r requirements.txt -c constraints.txt
npm install -g @anthropic-ai/claude-code && claude setup-token
cp .env.example .env  # Edit with DATABASE_URL and CLAUDE_CODE_OAUTH_TOKEN
```

### Code Quality

```bash
black crawler/       # Format
flake8 crawler/      # Lint
mypy crawler/        # Type check
```

### Testing

```bash
pytest tests/        # unit tests (analyzer batching/quota, source health, settings, editor)
```

Ad-hoc test scripts are in `scripts/`:
- `scripts/test_notifications.py` — test Slack/email delivery
- `scripts/test_html_generator.py` — test HTML generation
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

1. **Hydrate**: ephemeral Postgres is seeded from `docs/data/articles.parquet` (deduped by `(url_id, content_hash)`)
2. **Crawl**: `run_crawl_with_analysis()` spawns three spider subprocess groups (peer/r1/facilities); success requires ≥2 of 3 groups
3. **Analyze incrementally**: `ClaudeCodeAnalyzer.batch_analyze()` processes articles while the crawl runs; a final pass catches stragglers. Zero analyses with pending articles fails the run (unless quota-exhausted, which is resumable)
4. **Source health**: per-group `spider_health_<group>.json` reports merge into `docs/data/source_health.json`; domains failing 7 consecutive runs are auto-disabled and listed on `docs/source-health.html`
5. **Export**: `LocalExporter.export_all()` writes JSON/CSV/HTML/TXT to `output/`
6. **Website**: `HTMLReportGenerator` generates Drudge Report-style static site to both `output/` and `docs/`
7. **Notify**: optional Slack/email daily reports

### Key Modules

| Module | Purpose |
|--------|---------|
| `crawler/__main__.py` | Entry point, pipeline orchestration |
| `crawler/config/settings.py` | Pydantic Settings, all config from `.env`. Global instance: `from crawler.config.settings import settings`. `_institution_entries()` emits one entry per verified news source (primary + ai_tag + secondary, capped 3/institution) |
| `crawler/config/scrapy_defaults.py` | The single Scrapy settings dict shared by the spider and subprocess launcher |
| `crawler/spiders/university_spider.py` | Scrapy spider. Discovery = front page + RSS (with pubDate freshness) + sitemaps (lastmod-filtered, index recursion). RSS autodiscovery from `<link rel=alternate>` → `docs/data/discovered_feeds.json`. Undated articles excluded |
| `crawler/ai/claude_cli.py` | Headless Claude Code CLI runner (subscription auth), quota detection, preflight |
| `crawler/ai/claude_code_analyzer.py` | `ClaudeCodeAnalyzer` — batched structured-output analysis, resumable on quota exhaustion |
| `crawler/ai/editor.py` | `EditorialCurator` — Top News picks via one structured CLI call |
| `crawler/ai/themes.py` | Closed-vocabulary theme taxonomy helpers (`themes.json`) |
| `crawler/db/models.py` | SQLAlchemy ORM: `URL`, `Article`, `AIAnalysis`, `NotificationSent`, `HostCrawlState` |
| `crawler/db/session.py` | `DatabaseManager` — connection pooling, `create_tables()`, session management |
| `crawler/extractors/content.py` | `ContentExtractor` (Trafilatura wrapper) |
| `crawler/utils/source_health.py` | Rolling per-domain health, auto-disable/probe policy, HTML report |
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
- `r1_universities.json` (186 sources) — Carnegie R1 universities
- `major_facilities.json` (10 sources) — HPC & research centers
- `national_laboratories.json` (54 sources) — national labs: Argonne, Los Alamos, NIST, etc.
- `global_institutions.json` (102 sources) — international institutions

`settings.university_source_type = "all"` loads all five. Sources use schema v3.0.0 with `news_sources` arrays. Every entry with `verified: true` is crawled (primary + ai_tag + secondary, up to 3 per institution). RSS feeds are preferred over HTML when `USE_RSS_FEEDS=True`. One-off verification artifacts live in `archive/config/`.

### AI Analysis (actual behavior)

Single provider: Claude via the Claude Code CLI (`settings.claude_code_model`, default alias `sonnet`). One batched prompt covers ~15 articles and returns a JSON array validated against a schema: `is_ai_related`, `confidence` (0–1, stored as `ai_confidence_score`), `summary`, `key_points`, `relevance_score`, `themes` (validated against `crawler/config/themes.json`), and `impact_scores`. Results are written to the same `ai_analyses` columns as before; `openai_*`/`gemini_*` columns remain NULL for new rows.

### Website Generation

`HTMLReportGenerator` produces a Drudge Report-style static site with:
- **Three-column layout**: Peer Institutions | R1 Institutions | Major Facilities
- Classification via `UniversityClassifier` fuzzy-matching against source JSON files (priority: Facility > Peer > R1)
- **Dual output**: writes to both `output/` (local) and `docs/` (GitHub Pages, committed to `website` branch)
- Pages: `index.html` (last 5 days), `archive/YYYY-MM-DD.html` (daily), `archive/index.html` (file-scan based), `source-health.html`
- Styling: `Courier New` monospace, black/white/red (`#cc0000`), responsive (single column below 1024px)

### Database Tables

- **urls**: URL tracking, SHA-256 `url_hash`, crawl status, content change detection via `content_hash`
- **articles**: Extracted content, `is_ai_related` boolean, `ai_confidence_score`, `university_name`, JSONB `article_metadata` (includes `themes`, `impact_scores`, `date_estimated`, `discovered_via`)
- **ai_analyses**: Provider results + consensus summary (Claude-only going forward)
- **notifications_sent**: Delivery log per channel
- **host_crawl_state**: Per-domain crawl delays, `blocked_until`

Unique constraint on articles: `(url_id, content_hash)` enables detecting content updates at same URL.

## Output Directories

- `output/` — local output (gitignored): results JSON, CSV exports, HTML reports, per-group `spider_health_*.json`
- `docs/` — GitHub Pages (committed to `website` branch): `index.html`, `how_it_works.html`, `source-health.html`, `archive/`, `data/` (parquet snapshot, source health, discovered feeds)

## Custom Agents

`.claude/agents/url-verifier.md` — validates URLs from university news sources before content extraction.
