# AI University News Aggregator

Automated daily news aggregator tracking AI research and developments from 380+ universities, national laboratories, and research facilities worldwide.

**Live Site:** https://tyson-swetnam.github.io/webcrawler

## How it works

1. **Crawl** — Scrapy fans out over each source's news front page, RSS/Atom feeds, and sitemaps (explicit config, robots.txt `Sitemap:` lines, and `/sitemap.xml`), filtered by publication freshness.
2. **Extract** — Trafilatura pulls clean article text; publication dates fall back to htmldate and the discovery channel's date (RSS pubDate / sitemap lastmod). Undated pages are excluded.
3. **Dedupe** — SHA-256 URL and content hashing against PostgreSQL.
4. **Analyze** — Claude (via the Claude Code CLI) classifies AI relevance, summarizes, extracts key points, tags 1–5 themes from a fixed 22-theme taxonomy, and scores scientific/financial/partnership impact — ~15 articles per prompt.
5. **Curate** — Claude acts as daily news editor, picking up to 10 Top News stories from the past week, each with an editorial note and an impact category (Scientific Breakthrough / Major Funding / Strategic Partnership / Policy Impact).
6. **Snapshot** — the full article history is exported to `docs/data/articles.parquet` (with a pre-aggregated `themes_daily.parquet`), which both hydrates the next run's ephemeral database and feeds the analytics dashboard.
7. **Publish** — a static site is generated to `docs/`, a Pagefind full-text search index is built, and everything is pushed to the `website` branch for GitHub Pages.

## The website

- **Today** (`index.html`) — AI-related articles from the last 5 days in a dense tabbed list: **Top News**, All, Peer, R1, HPC, Labs, Global, with an inline filter box and expandable per-article summaries and topic pills.
- **Top News** — the editorial picks, ranked, with Claude's one-line rationale and impact badge. Picks persist in `docs/data/top_news.json` so the tab survives empty crawls.
- **Archive** — one page per day plus a monthly index with full-text search (Pagefind, with category/university/topic/date filters and popular-topic shortcuts).
- **Analytics** (`analytics.html`) — a DuckDB-WASM dashboard that queries the parquet snapshot directly in the browser: themes over time, impact-category distribution, a university leaderboard, articles per day, and a free-form SQL playground.
- **Source health** (`source-health.html`) — rolling per-domain crawl health with auto-disable of persistently dead sources.

## AI analysis: Claude Max subscription (no API keys)

Analysis runs through **Claude Code CLI headless mode**, authenticated with a Claude Max subscription OAuth token — there is no per-token API billing and no `ANTHROPIC_API_KEY`/`OPENAI_API_KEY`.

Setup:

```bash
npm install -g @anthropic-ai/claude-code
claude setup-token          # requires a Claude Pro/Max subscription; token lasts ~1 year
```

Put the token in `.env` as `CLAUDE_CODE_OAUTH_TOKEN` for local runs, and add it as the
`CLAUDE_CODE_OAUTH_TOKEN` **repository secret** for GitHub Actions.

Notes:

- Articles are batched (`AI_ARTICLES_PER_PROMPT`, default 15) so a full daily run costs a handful of subscription messages, not hundreds of API calls; editorial curation adds one more structured message per run. `AI_MESSAGE_BUDGET` (default 400) soft-caps messages per run.
- If the subscription's 5-hour/weekly usage window is exhausted mid-run, analysis stops cleanly; unanalyzed articles keep `last_analyzed = NULL` and are picked up by the next daily run.
- When the token expires (~1 year), the workflow's preflight step fails with instructions — rerun `claude setup-token` and update the secret.
- *Terms-of-service note:* Anthropic documents subscription OAuth as intended for "ordinary use of Claude Code". Personal, modest-volume automation on your own token (this project sends ~5–70 messages/day) is a gray area rather than explicitly sanctioned — this repo intentionally uses no third parties' credentials and does not resell access.

## Scheduling

**GitHub Actions is the production scheduler** (`.github/workflows/daily-crawler.yml`, daily at 15:00 UTC, plus `workflow_dispatch` for manual runs). Each run analyzes at most 1,000 articles and stops analysis at a 70-minute wall-clock deadline, so the snapshot export and site publish always complete inside the CI timeout — leftovers are picked up later. A companion **Backlog Analyzer** workflow (`backlog-processor.yml`) drains any remaining backlog in crawl-free chunks at 03:00/09:00/21:00 UTC, re-triggering itself until the backlog is empty.

## Development

```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt -c constraints.txt
cp .env.example .env    # set DATABASE_URL and CLAUDE_CODE_OAUTH_TOKEN

# run the full pipeline
python -m crawler

# run the tests
pytest tests/
```

## Source health

The crawler maintains a rolling per-domain health history (`docs/data/source_health.json`). Domains that fail 7 consecutive runs are auto-disabled (probed again every 7th run), and a report is published at `docs/source-health.html`. Newly discovered RSS feeds are suggested in `docs/data/discovered_feeds.json` for promotion into the source configs.

## Technology

- **Crawler:** Python + Scrapy (sitemap + RSS + front-page discovery, three parallel spider groups)
- **Extraction:** Trafilatura + htmldate
- **AI Analysis & Curation:** Claude via Claude Code CLI (Max subscription auth), structured JSON output
- **Storage:** PostgreSQL (ephemeral in CI, hydrated from a parquet snapshot) + DuckDB/Parquet
- **Search:** Pagefind static full-text index
- **Analytics:** DuckDB-WASM querying parquet in the browser
- **Deployment:** GitHub Actions → GitHub Pages (`website` branch)
