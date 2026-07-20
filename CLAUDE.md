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
4. Batched Claude analysis via the Claude Code CLI (~15 articles/prompt, structured JSON output: relevance, summary, key points, themes, impact scores)
5. Editorial curation — Claude picks up to 10 Top News stories from the last 7 days (one structured CLI call), persisted to `docs/data/top_news.json`
6. Parquet snapshot — full history exported to `docs/data/articles.parquet` + pre-aggregated `themes_daily.parquet` for the analytics dashboard
7. HTML report generation to both `output/` and `docs/`, plus a Pagefind full-text search index (`docs/pagefind/`)
8. Optional Slack/email notifications (disabled by default)

Debug a single university:
```bash
source venv/bin/activate && scrapy crawl university_news -a start_urls='["https://news.stanford.edu"]'
```

### AI Backend (Claude Max subscription)

Analysis calls go through `claude -p --output-format json --json-schema` (headless Claude Code CLI). Auth is the `CLAUDE_CODE_OAUTH_TOKEN` env var created with `claude setup-token` (~1-year lifetime). There are NO `ANTHROPIC_API_KEY`/`OPENAI_API_KEY` settings anymore.

- `crawler/ai/claude_cli.py` — low-level runner; raises `ClaudeQuotaExhausted` when the subscription window is used up (hard stop, not a 429)
- `crawler/ai/claude_code_analyzer.py` — batches `AI_ARTICLES_PER_PROMPT` (15) articles per message; failed/skipped articles keep `last_analyzed = NULL` so the next run resumes them
- `AI_MESSAGE_BUDGET` (400) soft-caps subscription messages per run
- `MAX_PIPELINE_MINUTES` (75 default, 70 in CI) wall-clock-caps crawl+analysis so the Parquet export and site publish always run before the CI step timeout; leftovers resume later
- `ANALYZE_ONLY=true` skips crawling and only drains the stored backlog (used by the Backlog Analyzer workflow)
- Never pass `--bare` to the CLI — it skips OAuth token reads

### Automated Execution

- **GitHub Actions is the production scheduler**: `.github/workflows/daily-crawler.yml` runs at 15:00 UTC, uses ephemeral PostgreSQL (hydrated from `docs/data/articles.parquet` on the `website` branch), installs a pinned Claude Code CLI, live-probes subscription auth in preflight (fast-fail on a bad/expired token), and publishes the site into `website:/docs` — the folder GitHub Pages serves — with rebase+retry. Per-run brakes (`MAX_ARTICLES_PER_RUN=1000`, `MAX_PIPELINE_MINUTES=70`) stop analysis early enough that the export/publish steps always beat the 90-minute step timeout. Requires the `CLAUDE_CODE_OAUTH_TOKEN` repository secret.
- **Backlog draining**: `.github/workflows/backlog-processor.yml` ("Backlog Analyzer") runs crawl-free `ANALYZE_ONLY` chunks (~1,500 articles) at 03:00/09:00/21:00 UTC and re-triggers itself via `workflow_dispatch` (bounded by a `remaining_runs` budget) while backlog remains. Both workflows share the `website-publish` concurrency group so they queue instead of racing pushes to the `website` branch.
- **Archive backfill**: `.github/workflows/backfill-archive.yml` ("Archive Backfill", manual dispatch only) recovers from crawler outages: it crawls/analyzes with a wide `MAX_ARTICLE_AGE_DAYS` window derived from a `start_date` input (so the 30-day filter doesn't exclude gap articles), self-chains like the Backlog Analyzer, and runs `scripts/regenerate_all_archives.py` to rebuild per-publication-date archive pages and the Pagefind index.
- GitHub Actions is the only scheduler. The old self-hosted systemd/cron runner was decommissioned in July 2026 and its deployment files removed.

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
3. **Analyze incrementally**: `ClaudeCodeAnalyzer.batch_analyze()` processes articles while the crawl runs; `drain_unanalyzed()` catches stragglers afterwards. Analysis stops cleanly at the `max_pipeline_minutes` wall-clock deadline or the `max_articles_per_run` cap so later phases always run; `analyze_only` mode skips the crawl entirely (Backlog Analyzer). Zero analyses with pending articles fails the run, unless the stop was expected (quota, deadline, cap)
4. **Source health**: per-group `spider_health_<group>.json` reports merge into `docs/data/source_health.json`; domains failing 7 consecutive runs are auto-disabled and listed on `docs/source-health.html`
5. **Curate**: `EditorialCurator.curate_top_news()` ranks the top ~50 candidates (last 7 days, by composite impact score) and has Claude pick ≤10 Top News stories with editorial notes and impact categories; snapshot saved to `docs/data/top_news.json` so the tab survives empty runs
6. **Snapshot**: `ParquetStore.export_from_postgres()` writes `docs/data/articles.parquet` (editorial picks stamped on), plus `export_themes_daily()` → `themes_daily.parquet` for the dashboard
7. **Export**: `LocalExporter.export_all()` writes JSON/CSV/HTML/TXT to `output/`
8. **Website**: `HTMLReportGenerator` renders the static site to both `output/` and `docs/`; per-article search stubs are indexed with the `pagefind` CLI into `docs/pagefind/`
9. **Notify**: optional Slack/email daily reports

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
| `crawler/ai/themes.py` | Closed-vocabulary theme taxonomy helpers (`themes.json`, 22 theme ids) |
| `crawler/storage/parquet_store.py` | `ParquetStore` — durable Parquet source of truth (`articles.parquet`, `themes_daily.parquet`), bi-directional Postgres sync, stable hash-derived ids. `pending_content` carries full text for unanalyzed articles only, so the backlog survives ephemeral CI databases |
| `crawler/db/models.py` | SQLAlchemy ORM: `URL`, `Article`, `AIAnalysis`, `NotificationSent`, `HostCrawlState` |
| `crawler/db/session.py` | `DatabaseManager` — connection pooling, `create_tables()`, session management |
| `crawler/extractors/content.py` | `ContentExtractor` (Trafilatura wrapper) |
| `crawler/utils/source_health.py` | Rolling per-domain health, auto-disable/probe policy, HTML report |
| `crawler/utils/html_generator.py` | `HTMLReportGenerator` — renders the static website (tabbed dense-list layout, Top News, archive, Pagefind search stubs, How It Works page) |
| `crawler/utils/university_classifier.py` | `UniversityClassifier` — classifies articles into peer/r1/hpc/national_lab/global (priority: national_lab > hpc > peer > global > r1) |
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

Single provider: Claude via the Claude Code CLI (`settings.claude_code_model`, default alias `sonnet`). One batched prompt covers ~15 articles and returns a JSON array validated against a schema: `is_ai_related`, `confidence` (0–1, stored as `ai_confidence_score`), `summary`, `key_points` (≤5), `relevance_score` (1–10), `themes` (1–5 ids validated against `crawler/config/themes.json`), and `impact_scores` (`scientific`/`financial`/`partnership`, each 1–10). Themes and impact scores are stored on `article_metadata` so they flow into the Parquet snapshot. Results are written to the same `ai_analyses` columns as before; `openai_*`/`gemini_*` columns remain NULL for new rows.

A separate `EditorialCurator` call (`crawler/ai/editor.py`) selects Top News: candidates from the last 7 days are ranked by composite impact score (top 50), and one structured prompt returns ≤10 picks with `rank`, `editorial_note`, and an `impact_category` from: Scientific Breakthrough, Major Funding, Strategic Partnership, Policy Impact.

### Website Generation

`HTMLReportGenerator` produces a static site with:
- **Tabbed dense-list layout** on the front page: Top News | All | Peer | R1 | HPC | Labs | Global, with per-category color dots, an inline filter box, expandable rows (summary + topic pills), and a 25-row "show more" cap per tab
- **Top News tab**: editorial picks with rank, impact badge, and editorial note; falls back to the persisted snapshot `docs/data/top_news.json` when the current run has no picks
- Classification via `UniversityClassifier` fuzzy-matching against source JSON files (priority: national_lab > hpc > peer > global > r1; default r1)
- **Dual output**: writes to both `output/` (local) and `docs/` (GitHub Pages, committed to `website` branch)
- Pages: `index.html` (AI-related articles from the last 5 days), `archive/YYYY-MM-DD.html` (daily), `archive/index.html` (file-scan based, monthly grouping, Pagefind search UI + popular-topic pills), `how_it_works.html` (regenerated every run), `source-health.html`
- `analytics.html` is a **static, hand-maintained page** (not generated) — a DuckDB-WASM dashboard that queries `data/articles.parquet` + `data/themes_daily.parquet` in the browser: themes over time, impact-category distribution, university leaderboard, articles per day, and an SQL playground
- **Search**: `generate_search_stubs()` emits per-article HTML stubs that the `pagefind` CLI indexes into `docs/pagefind/` (filters: category, university, topic, date)
- Styling: DM Sans (Google Fonts), light minimal design with CSS custom properties, responsive

### Database Tables

- **urls**: URL tracking, SHA-256 `url_hash`, crawl status, content change detection via `content_hash`
- **articles**: Extracted content, `is_ai_related` boolean, `ai_confidence_score`, `university_name`, JSONB `article_metadata` (includes `themes`, `impact_scores`, `date_estimated`, `discovered_via`)
- **ai_analyses**: Provider results + consensus summary (Claude-only going forward)
- **notifications_sent**: Delivery log per channel
- **host_crawl_state**: Per-domain crawl delays, `blocked_until`

Unique constraint on articles: `(url_id, content_hash)` enables detecting content updates at same URL.

## Output Directories

- `output/` — local output (gitignored): results JSON, CSV exports, HTML reports, per-group `spider_health_*.json`
- `docs/` — GitHub Pages (committed to `website` branch): `index.html`, `analytics.html`, `how_it_works.html`, `source-health.html`, `archive/`, `pagefind/` (search index), `data/` (`articles.parquet`, `themes_daily.parquet`, `top_news.json`, `source_health.json`, `discovered_feeds.json`)

## Custom Agents

`.claude/agents/url-verifier.md` — validates URLs from university news sources before content extraction.
