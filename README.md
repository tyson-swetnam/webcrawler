# AI University News Aggregator

Automated daily news aggregator tracking AI research and developments from 380+ universities, national laboratories, and research facilities worldwide.

**Live Site:** https://tyson-swetnam.github.io/webcrawler

## How it works

1. **Crawl** — Scrapy fans out over each source's news front page, RSS/Atom feeds, and sitemaps (explicit config, robots.txt `Sitemap:` lines, and `/sitemap.xml`), filtered by publication freshness.
2. **Extract** — Trafilatura pulls clean article text; publication dates fall back to htmldate and the discovery channel's date (RSS pubDate / sitemap lastmod). Undated pages are excluded.
3. **Dedupe** — SHA-256 URL and content hashing against PostgreSQL.
4. **Analyze** — Claude (via the Claude Code CLI) classifies AI relevance, summarizes, tags themes, and scores impact — ~15 articles per prompt.
5. **Publish** — a Drudge Report-style static site is generated to `docs/` and pushed to the `website` branch for GitHub Pages.

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

- Articles are batched (`AI_ARTICLES_PER_PROMPT`, default 15) so a full daily run costs a handful of subscription messages, not hundreds of API calls.
- If the subscription's 5-hour/weekly usage window is exhausted mid-run, analysis stops cleanly; unanalyzed articles keep `last_analyzed = NULL` and are picked up by the next daily run.
- When the token expires (~1 year), the workflow's preflight step fails with instructions — rerun `claude setup-token` and update the secret.
- *Terms-of-service note:* Anthropic documents subscription OAuth as intended for "ordinary use of Claude Code". Personal, modest-volume automation on your own token (this project sends ~5–70 messages/day) is a gray area rather than explicitly sanctioned — this repo intentionally uses no third parties' credentials and does not resell access.

## Scheduling

**GitHub Actions is the production scheduler** (`.github/workflows/daily-crawler.yml`, daily at 15:00 UTC, plus `workflow_dispatch` for manual runs). The old systemd/cron runners under `deployment/` and `scripts/` are deprecated — disable any local timer with `sudo systemctl disable --now ai-news-crawler.timer` so it doesn't race the workflow on the `website` branch.

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

- **Crawler:** Python + Scrapy (sitemap + RSS + front-page discovery)
- **Extraction:** Trafilatura + htmldate
- **AI Analysis:** Claude via Claude Code CLI (Max subscription auth)
- **Storage:** PostgreSQL (ephemeral in CI, hydrated from a parquet snapshot) + DuckDB/Parquet
- **Deployment:** GitHub Actions → GitHub Pages (`website` branch)
