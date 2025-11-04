# AI University News Aggregator

**Live Site:** https://tyson-swetnam.github.io/webcrawler

Automated daily news aggregator tracking AI research and developments from 241+ US universities and research facilities. Features AI-powered content analysis, smart deduplication, and a clean Drudge Report-style interface.

**Last Updated:** Auto-updates daily at 07:00 PST via GitHub Actions

---

## What It Does

This system automatically crawls university news sites daily, identifies AI-related research announcements, and publishes them to a clean, mobile-responsive website. It leverages multiple AI APIs (Claude, GPT) to analyze content quality and relevance, ensuring only genuine AI research news makes it to the front page.

### Key Features

- **Automated Daily Crawls** - Runs at 07:00 PST via GitHub Actions
- **241+ Sources** - 27 peer institutions, 187 R1 universities, 27 major research facilities
- **Multi-AI Analysis** - Powered by Claude (Anthropic) and GPT (OpenAI) for content classification
- **Smart Deduplication** - SHA-256 hashing prevents duplicate articles across sites
- **30-Day Rolling Window** - Only recent news (configurable age limit)
- **GitHub Pages Publishing** - Zero-cost hosting with automatic deployment
- **Ethical Crawling** - Respects robots.txt, implements rate limiting, descriptive User-Agent

---

## Architecture

The system runs as a **single-pipeline orchestrator** with 6 distinct phases:

```
┌─────────────────────────────────────────────────────────────────┐
│  GitHub Actions (Daily at 07:00 PST)                            │
│  Triggered: Schedule or Manual                                  │
└─────────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────────┐
│  Phase 1: Discovery & Crawling (Scrapy)                         │
│  - Respects robots.txt and crawl delays                         │
│  - Concurrent requests with politeness controls                 │
│  - Stores URLs in PostgreSQL with hash-based deduplication      │
└─────────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────────┐
│  Phase 2: Content Extraction (Trafilatura)                      │
│  - Extracts clean text from HTML (95%+ accuracy)                │
│  - Parses metadata: author, publish date, word count            │
│  - Filters articles by age (default: 30 days)                   │
└─────────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────────┐
│  Phase 3: Deduplication (PostgreSQL + SHA-256)                  │
│  - URL hash: Detect previously seen links                       │
│  - Content hash: Identify duplicate articles with different URLs│
│  - Two-level filtering prevents re-processing                   │
└─────────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────────┐
│  Phase 4: AI Analysis (Claude + GPT)                            │
│  - Parallel API calls for speed                                 │
│  - Consensus-based relevance scoring                            │
│  - Claude Sonnet-4-5 for primary summaries                      │
│  - GPT-4 for category classification                            │
└─────────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────────┐
│  Phase 5: HTML Generation                                       │
│  - Drudge Report-style responsive design                        │
│  - Outputs to docs/ folder for GitHub Pages                     │
│  - Generates archive index and metadata                         │
└─────────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────────┐
│  Phase 6: Deployment                                            │
│  - Commits HTML to 'website' branch                             │
│  - GitHub Pages auto-deploys changes                            │
│  - Live site updated in ~30 seconds                             │
└─────────────────────────────────────────────────────────────────┘
```

**Entry Point:** `python -m crawler` (runs all 6 phases sequentially)

**Total Execution Time:** ~3-4 minutes from crawl start to live website

---

## Technology Stack

### Core Framework
- **Python 3.11+** - Modern async/await support
- **Scrapy 2.12+** - Production-grade web crawling
- **Trafilatura 1.6+** - Content extraction with 95%+ accuracy
- **PostgreSQL 15+** - Metadata and tracking database
- **SQLAlchemy 2.0+** - ORM with type safety

### AI Integration
- **Anthropic Claude (Sonnet-4-5)** - Primary analysis and summaries
- **OpenAI GPT-4** - Secondary analysis and categorization
- **Async/await** - Parallel API calls for speed
- **Graceful degradation** - System works if 1 API fails

### Deployment
- **GitHub Actions** - Daily automated execution (free for public repos)
- **GitHub Pages** - Zero-cost static site hosting
- **Systemd** - Optional local deployment via timers

### Monitoring (Optional)
- **Slack Webhooks** - Daily summary notifications
- **SMTP Email** - HTML email reports
- **JSON/CSV Export** - Local file exports for analysis

---

## Quick Start

### 1. Clone Repository

```bash
git clone https://github.com/tyson-swetnam/webcrawler.git
cd webcrawler
```

### 2. Environment Setup

```bash
# Create virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Configure environment variables
cp .env.example .env
# Edit .env with your API keys
```

### 3. Database Setup

```bash
# Option A: PostgreSQL (production)
sudo -u postgres psql
CREATE DATABASE ai_news_crawler;
CREATE USER crawler WITH PASSWORD 'your_secure_password';
GRANT ALL PRIVILEGES ON DATABASE ai_news_crawler TO crawler;
\q

# Set DATABASE_URL in .env:
# DATABASE_URL=postgresql://crawler:your_secure_password@localhost:5432/ai_news_crawler

# Option B: SQLite (testing only - not recommended for production)
# DATABASE_URL=sqlite:///./crawler.db
```

### 4. Run the Crawler

```bash
# Run complete pipeline (all 6 phases)
python -m crawler

# View generated HTML locally
cd output
python -m http.server 8000
# Visit: http://localhost:8000
```

---

## Production Deployment

### GitHub Actions (Recommended)

This is the primary deployment method used for https://tyson-swetnam.github.io/webcrawler

**Prerequisites:**
- GitHub repository (public or private)
- API keys for Claude and/or OpenAI

**Setup Steps:**

1. **Configure GitHub Secrets**
   - Go to: `Settings` → `Secrets and variables` → `Actions`
   - Add secrets:
     ```
     ANTHROPIC_API_KEY=sk-ant-xxxxx
     OPENAI_API_KEY=sk-xxxxx
     SLACK_WEBHOOK_URL=https://hooks.slack.com/... (optional)
     ```

2. **Enable GitHub Pages**
   - Go to: `Settings` → `Pages`
   - Source: `Deploy from a branch`
   - Branch: `website` → `/ (root)`
   - Click **Save**

3. **Push Workflow**
   ```bash
   git add .github/workflows/daily-crawler.yml
   git commit -m "Add GitHub Actions workflow"
   git push origin main
   ```

4. **Trigger First Run**
   - **Option A:** Wait for 07:00 PST scheduled run
   - **Option B:** Manual trigger via `Actions` tab → `Run workflow`

5. **Verify Deployment**
   - Check `Actions` tab for green checkmark
   - Visit: `https://YOUR-USERNAME.github.io/YOUR-REPO-NAME`

**Workflow Configuration:** `.github/workflows/daily-crawler.yml`

**Schedule:** Daily at 07:00 PST (15:00 UTC)

**Cost:** Free (GitHub Actions provides unlimited minutes for public repos)

See [GITHUB_PAGES_SETUP.md](GITHUB_PAGES_SETUP.md) for detailed instructions.

---

### Local Systemd Deployment (Alternative)

For running on your own Linux server:

```bash
# Deploy service and timer
sudo bash scripts/deploy.sh

# Check status
systemctl status ai-news-crawler.timer
systemctl list-timers --all

# Manual trigger
sudo systemctl start ai-news-crawler.service

# View logs
journalctl -u ai-news-crawler -f
```

**Service files:** `deployment/ai-news-crawler.service`, `deployment/ai-news-crawler.timer`

---

## Configuration

All settings are managed via environment variables (`.env` file or GitHub Secrets).

### Required Settings

```bash
# Database
DATABASE_URL=postgresql://user:pass@localhost:5432/ai_news_crawler

# AI APIs (at least one required)
ANTHROPIC_API_KEY=sk-ant-xxxxx
OPENAI_API_KEY=sk-xxxxx
```

### Optional Settings

```bash
# Crawling behavior
MAX_CONCURRENT_REQUESTS=50        # Crawl speed (default: 50)
CRAWL_DELAY=1.0                   # Seconds between requests (default: 1.0)
MAX_ARTICLE_AGE_DAYS=30           # Skip articles older than this (default: 30)
MAX_ARTICLES_PER_RUN=1000         # Limit per execution (default: 1000)

# AI Analysis
ENABLE_AI_ANALYSIS=true           # Enable/disable AI analysis (default: true)
AI_ANALYSIS_BATCH_SIZE=10         # Concurrent AI requests (default: 10)

# Notifications
ENABLE_SLACK_NOTIFICATIONS=false  # Slack webhook (default: false)
ENABLE_EMAIL_NOTIFICATIONS=false  # SMTP email (default: false)
SLACK_WEBHOOK_URL=https://...     # If Slack enabled
SMTP_HOST=smtp.gmail.com          # If email enabled
SMTP_PORT=465
SMTP_PASSWORD=app-password
EMAIL_FROM=crawler@example.com
EMAIL_TO=["you@example.com"]

# Output
SAVE_RESULTS_TO_FILE=true         # Export JSON/CSV/HTML (default: true)
LOCAL_OUTPUT_DIR=./output         # Local export directory (default: ./output)

# Logging
DEBUG=false                       # Debug mode (default: false)
LOG_LEVEL=INFO                    # Logging verbosity (default: INFO)
```

See [CLAUDE.md](CLAUDE.md) for complete configuration reference.

---

## Project Structure

```
webcrawler/
├── .github/
│   └── workflows/
│       └── daily-crawler.yml          # GitHub Actions workflow
├── crawler/                            # Main application package
│   ├── __main__.py                    # Entry point: python -m crawler
│   ├── config/
│   │   ├── settings.py                # Pydantic configuration
│   │   └── universities.json          # 241 university sources
│   ├── spiders/
│   │   └── university_spider.py       # Scrapy spider
│   ├── ai/
│   │   ├── claude.py                  # Claude API client
│   │   ├── openai_client.py           # OpenAI API client
│   │   └── analyzer.py                # Multi-AI orchestration
│   ├── db/
│   │   ├── models.py                  # SQLAlchemy ORM models
│   │   └── session.py                 # Database connection
│   ├── notifiers/
│   │   ├── slack.py                   # Slack webhook
│   │   └── email.py                   # SMTP email
│   └── utils/
│       ├── html_generator.py          # Drudge-style HTML generator
│       ├── local_exporter.py          # JSON/CSV export
│       └── deduplication.py           # Hash-based dedup
├── deployment/
│   ├── ai-news-crawler.service        # Systemd service
│   └── ai-news-crawler.timer          # Systemd timer
├── scripts/
│   ├── deploy.sh                      # Automated deployment
│   └── daily_crawl_and_publish.sh     # Manual crawl + commit script
├── docs/                               # GitHub Pages output (auto-generated)
│   ├── index.html                     # Main news page
│   └── archive/
│       └── index.html                 # Historical archive
├── tests/
│   ├── unit/                          # Unit tests
│   └── integration/                   # Integration tests
├── requirements.txt                    # Python dependencies
├── .env.example                       # Example environment config
├── CLAUDE.md                          # Developer guide for Claude Code
├── GITHUB_PAGES_SETUP.md              # GitHub Actions deployment guide
└── README.md                          # This file
```

---

## Database Schema

### Core Tables

- **urls** - URL tracking with SHA-256 hash-based deduplication
- **articles** - Extracted content with metadata (title, author, date, word count)
- **ai_analyses** - Results from Claude and GPT APIs with consensus summaries
- **notifications_sent** - Notification delivery log (Slack, email)
- **host_crawl_state** - Per-domain politeness tracking (crawl delays, backoff)

**Key Design Decisions:**
- Two-level hashing: URL hash + content hash for robust deduplication
- PostgreSQL indexes optimized for common queries (recent articles, AI-related content)
- JSONB metadata field for flexible schema evolution
- Connection pooling (default: 100 connections for GitHub Actions parallelism)

---

## Development

### Running Tests

```bash
# All tests
pytest

# Unit tests only
pytest tests/unit/

# Integration tests (requires database)
pytest tests/integration/

# Specific test file
pytest tests/unit/test_ai_clients.py -v
```

### Code Quality

```bash
# Format code
black crawler/

# Lint
flake8 crawler/

# Type checking
mypy crawler/
```

### Database Migrations

```bash
# Create new migration
alembic revision --autogenerate -m "description"

# Apply migrations
alembic upgrade head

# Rollback
alembic downgrade -1
```

---

## Cost Estimates

### GitHub Actions (Free)
- **Public repos:** Unlimited minutes
- **This workflow:** ~4 minutes/day = 120 minutes/month
- **Cost:** $0/month

### AI API Costs (Estimated)
Assuming 100 articles/day analyzed:

- **Claude Sonnet-4-5:** ~$9/month
- **GPT-4:** ~$27/month
- **Total:** ~$36/month

**Optimization Tips:**
1. Use `MAX_ARTICLES_PER_RUN` to limit daily volume
2. Increase `MAX_ARTICLE_AGE_DAYS` to reduce duplicate processing
3. Set `ENABLE_AI_ANALYSIS=false` to test crawling without API costs

---

## Web Crawling Ethics

This project follows ethical web crawling best practices:

- **Respects robots.txt** - Always honors site preferences
- **Rate limiting** - Default 1 request/second per domain
- **Descriptive User-Agent** - Identifies crawler with contact info
- **Politeness delays** - Implements exponential backoff for failures
- **Concurrent limits** - Max 1 concurrent request per domain
- **Timeout handling** - Avoids hanging on slow responses

**User-Agent String:**
```
AI-University-News-Crawler/1.0 (+https://github.com/tyson-swetnam/webcrawler)
```

---

## Monitoring & Troubleshooting

### GitHub Actions Status

- **Actions Tab:** See all runs and their status
- **Email Notifications:** GitHub sends alerts for failed workflows
- **Logs:** Click on any run to see detailed execution logs

### Common Issues

**Workflow Fails with "Database Error"**
- Cause: PostgreSQL service not ready
- Fix: Workflow includes health checks; usually resolves automatically

**No HTML Generated**
- Cause: Crawler found no new articles (normal if sites haven't updated)
- Fix: HTML still updates with empty state; check logs for crawl results

**Website Not Updating**
- Causes: Failed Actions run, or website branch not deploying
- Fix: Check Actions tab, verify website branch has new commits, check Pages settings

**API Rate Limits**
- Cause: Too many API calls in short time
- Fix: Reduce `AI_ANALYSIS_BATCH_SIZE` or `MAX_CONCURRENT_REQUESTS`

---

## Contributing

Contributions are welcome! This project uses Claude Code for AI-assisted development.

### Development Workflow

1. Fork the repository
2. Create a feature branch: `git checkout -b feature-name`
3. Make your changes
4. Run tests: `pytest`
5. Format code: `black crawler/`
6. Commit changes: `git commit -m "Description"`
7. Push to fork: `git push origin feature-name`
8. Open a Pull Request

### Custom Agents

This repository includes specialized Claude Code agents in `.claude/agents/`:
- **python-web-crawler-architect** - Expert guidance on web crawling and data pipelines
- **architect-agent** - Orchestrates complex development workflows

See [CLAUDE.md](CLAUDE.md) for developer guidelines.

---

## Security

- **API Keys:** Never commit `.env` files (in `.gitignore`)
- **GitHub Secrets:** Encrypted and not exposed in logs
- **Database:** Fresh PostgreSQL instance per GitHub Actions run (no persistent data)
- **SMTP:** Use app passwords, not account passwords
- **File Permissions:** Set `chmod 600 .env` for local deployments
- **URL Validation:** Prevents SSRF attacks via strict URL filtering

---

## License

This project is open source. See LICENSE file for details.

---

## Links

- **Live Site:** https://tyson-swetnam.github.io/webcrawler
- **GitHub Repository:** https://github.com/tyson-swetnam/webcrawler
- **Issue Tracker:** https://github.com/tyson-swetnam/webcrawler/issues

---

## Acknowledgments

- **Claude Code** - AI-assisted development tool from Anthropic
- **Anthropic Claude API** - Primary AI analysis engine
- **OpenAI GPT API** - Secondary AI analysis
- **Scrapy Framework** - Production-grade web crawling
- **Trafilatura** - High-accuracy content extraction
- **GitHub Actions** - Free CI/CD for open source

---

*Automated with GitHub Actions | Generated with [Claude Code](https://claude.com/claude-code)*
