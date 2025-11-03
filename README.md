# AI University News Crawler

A production-grade Python web crawler that automatically discovers, extracts, and analyzes AI-related news from top US university press releases. The system uses multiple AI APIs (Claude Haiku, OpenAI, Gemini) to intelligently identify relevant content and delivers formatted summaries via Slack and email.

## How It Works

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    AI UNIVERSITY NEWS CRAWLER WORKFLOW                  │
└─────────────────────────────────────────────────────────────────────────┘

   1. DISCOVERY                2. EXTRACTION           3. DEDUPLICATION
   ═════════════               ═══════════════         ════════════════

   University Websites         Raw HTML Content        URL + Content Hash
   ┌──────────────┐           ┌──────────────┐        ┌──────────────┐
   │ Stanford.edu │           │ <html>...</> │        │  SHA-256     │
   │ MIT.edu      │──Scrapy──▶│ <article>... │──┬────▶│  Hashing     │
   │ CMU.edu      │  Spider   │ <h1>Title... │  │     │  Engine      │
   │ Berkeley.edu │           │ <p>Text...   │  │     └──────┬───────┘
   └──────────────┘           └──────────────┘  │            │
         │                          │            │            ▼
         │                          │            │     ┌─────────────┐
         │                          │            │     │ PostgreSQL  │
         │                          │            │     │ Seen URLs?  │
         │                          │            │     └─────┬───────┘
         │                          │            │           │
         │                          │            │      [NEW]│[SKIP]
         │                          │            │           ▼
         │                          │            │    Continue Pipeline
         │                          │            │
         │                          ▼            │
         │                  ┌──────────────┐    │
         │                  │ Trafilatura  │◀───┘
         │                  │  Extractor   │
         │                  └──────┬───────┘
         │                         │
         │                         ▼
         │                  Clean Article Data:
         │                  • Title
         │                  • Author
         │                  • Date
         │                  • Full Text
         │                         │
         └─────────────────────────┘

   4. AI CLASSIFICATION            5. ANALYSIS              6. DELIVERY
   ════════════════════            ═══════════              ═══════════

   ┌─────────────────────┐        ┌──────────────┐        ┌──────────┐
   │ Is this AI-related? │        │ Claude API   │        │  Slack   │
   │                     │        │ (Haiku 4.5)  │        │ Webhook  │
   │  Article Text       │        └──────┬───────┘        └────▲─────┘
   └─────────┬───────────┘               │                     │
             │                            ▼                     │
             │                     Deep Summary &         ┌────┴─────┐
             ├──────────▶ Claude  Research Analysis      │ Formatted│
             │                                            │ Reports  │
             ├──────────▶ OpenAI  ┌──────────────┐       └────▲─────┘
             │                    │ OpenAI GPT-4 │            │
             └──────────▶ Gemini  └──────┬───────┘            │
                                         │                     │
                   [Parallel Processing] │              ┌──────┴─────┐
                                         ▼              │   Email    │
                                  ┌──────────────┐     │ (HTML/SMTP)│
                                  │ Gemini API   │     └────────────┘
                                  │ (2.5 Flash)  │
                                  └──────┬───────┘
                                         │
                   ┌─────────────────────┴─────────────────────┐
                   ▼                                             ▼
            AI-Related? ────NO───▶ [Skip]                [Store All Results]
                   │                                             │
                  YES                                            ▼
                   │                                      ┌─────────────┐
                   └────────────────────────────────────▶ │ PostgreSQL  │
                                                          │  Database   │
                                                          └─────────────┘
                                                          • Articles
                                                          • AI Analyses
                                                          • Notifications
                                                          • Crawl History
```

## Key Features

- **Automated Daily Crawling**: Scrapy-based spider crawls 15+ top university news sites
- **Intelligent Content Extraction**: Trafilatura extracts clean article text with 95%+ accuracy
- **Multi-AI Consensus**: Parallel processing with Claude Haiku 4.5, GPT-4, and Gemini 2.5 Flash
- **Smart Deduplication**: SHA-256 hash-based URL and content fingerprinting prevents duplicates
- **Dual Notification Channels**: Rich formatted reports via Slack webhooks and HTML email
- **Production-Ready**: Systemd timers, database migrations, comprehensive logging
- **Ethical Crawling**: Respects robots.txt, implements rate limiting, configurable delays per domain

## Quick Start

### Prerequisites

- **Python 3.11+**
- **PostgreSQL 15+**
- **API Keys**: Claude, OpenAI, Gemini
- **Notification**: Slack webhook URL and/or SMTP email credentials

### 1. Installation

```bash
# Clone repository
git clone https://github.com/yourusername/ai-news-crawler.git
cd ai-news-crawler

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Database Setup

```bash
# Create PostgreSQL database
sudo -u postgres psql
CREATE DATABASE ai_news_crawler;
CREATE USER crawler WITH PASSWORD 'your_secure_password';
GRANT ALL PRIVILEGES ON DATABASE ai_news_crawler TO crawler;
\q

# Run migrations
alembic upgrade head
```

### 3. Configuration

```bash
# Copy environment template
cp .env.example .env

# Edit with your credentials (use nano, vim, or any text editor)
nano .env
```

**Required environment variables:**

```bash
# Database
DATABASE_URL=postgresql://crawler:your_password@localhost:5432/ai_news_crawler

# AI API Keys
ANTHROPIC_API_KEY=sk-ant-xxx...  # Get from https://console.anthropic.com/
OPENAI_API_KEY=sk-xxx...         # Get from https://platform.openai.com/api-keys
GEMINI_API_KEY=xxx...            # Get from https://aistudio.google.com/app/apikey

# Notifications
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/xxx/xxx/xxx
EMAIL_FROM=your-email@gmail.com
EMAIL_TO=recipient@example.com
SMTP_PASSWORD=your-app-password  # For Gmail: use App Password, not account password
```

### 4. Run the Crawler

```bash
# Manual run (one-time execution)
python -m crawler

# View logs
tail -f logs/crawler.log

# Test notifications (without crawling)
python scripts/test_notifications.py
```

### 5. Enable Automated Daily Runs (Optional)

```bash
# Copy systemd service files
sudo cp deployment/ai-news-crawler.service /etc/systemd/system/
sudo cp deployment/ai-news-crawler.timer /etc/systemd/system/

# Update the service file with your paths
sudo nano /etc/systemd/system/ai-news-crawler.service

# Enable and start timer
sudo systemctl daemon-reload
sudo systemctl enable ai-news-crawler.timer
sudo systemctl start ai-news-crawler.timer

# Check status
systemctl status ai-news-crawler.timer
systemctl list-timers --all

# View logs
journalctl -u ai-news-crawler -f
```

## How the AI Classification Works

The crawler uses a **multi-AI consensus approach** for high accuracy:

1. **Initial Filtering**: All three AI APIs (Claude, OpenAI, Gemini) analyze each article in parallel
2. **AI-Related Detection**: Articles must contain keywords/topics related to:
   - Machine Learning / Deep Learning
   - Natural Language Processing
   - Computer Vision
   - Robotics & Autonomous Systems
   - AI Ethics & Policy
   - Neural Networks & AI Research

3. **Consensus Building**:
   - **Claude Haiku 4.5** is the primary analyzer (fast and cost-effective)
   - **GPT-4** provides secondary validation
   - **Gemini 2.5 Flash** offers additional fast screening

4. **Smart Summaries**: Claude Haiku generates concise summaries for each AI-related article

## Project Structure

```
ai-news-crawler/
├── crawler/                     # Main application package
│   ├── __main__.py              # Entry point: python -m crawler
│   ├── config/
│   │   ├── settings.py          # Pydantic configuration from .env
│   │   ├── logging.yaml         # Logging configuration
│   │   ├── universities.json    # University news source list
│   │   └── setup_logging.py     # Logging initialization
│   ├── spiders/
│   │   └── university_spider.py # Main Scrapy spider
│   ├── extractors/
│   │   └── content.py           # Trafilatura content extraction
│   ├── db/
│   │   ├── models.py            # SQLAlchemy database models
│   │   └── session.py           # Database connection pooling
│   ├── ai/
│   │   ├── analyzer.py          # Multi-AI orchestration
│   │   ├── claude.py            # Claude API client
│   │   ├── openai_client.py     # OpenAI API client
│   │   └── gemini.py            # Gemini API client
│   ├── notifiers/
│   │   ├── slack.py             # Slack webhook integration
│   │   └── email.py             # SMTP email sender
│   └── utils/
│       ├── deduplication.py     # SHA-256 hash-based deduplication
│       ├── rate_limiter.py      # Politeness rate limiting
│       ├── html_generator.py    # HTML report generation
│       └── local_exporter.py    # JSON/CSV export utilities
├── deployment/
│   ├── ai-news-crawler.service  # Systemd service unit
│   └── ai-news-crawler.timer    # Systemd timer (daily execution)
├── scripts/                     # Utility scripts
│   ├── deploy.sh                # Automated deployment
│   ├── setup_database.sh        # Database initialization
│   ├── test_notifications.py    # Test Slack/email delivery
│   ├── test_database.sh         # Database connectivity test
│   ├── generate_html_report.py  # Generate standalone HTML report
│   └── validate_universities.py # Validate university sources
├── output/                      # Crawl results (JSON, CSV, HTML)
├── logs/                        # Application logs
├── requirements.txt             # Python dependencies
├── alembic.ini                  # Database migration config
├── .env.example                 # Environment template
└── README.md                    # This file
```

## Configuration

### Adding Universities

Edit `crawler/config/universities.json`:

```json
{
  "universities": [
    {
      "name": "Stanford University",
      "news_url": "https://news.stanford.edu/",
      "location": "Stanford, CA",
      "focus_areas": ["Machine Learning", "NLP", "Computer Vision"]
    }
  ]
}
```

### Crawler Behavior Settings

In `.env` file:

```bash
# Crawling politeness
MAX_CONCURRENT_REQUESTS=8        # Max parallel requests
CRAWL_DELAY=1.0                  # Seconds between requests per domain
REQUEST_TIMEOUT=30               # Request timeout in seconds
ROBOTSTXT_OBEY=true             # Respect robots.txt (recommended)

# Content filtering
MIN_ARTICLE_LENGTH=100           # Minimum article length in characters
MAX_ARTICLE_AGE_DAYS=30          # Only crawl articles from last N days
LOOKBACK_DAYS=1                  # Daily mode: look back 1 day

# AI analysis
AI_ANALYSIS_BATCH_SIZE=5         # Articles to analyze per batch
MAX_ARTICLES_PER_RUN=1000        # Max articles to process per run
CLAUDE_MODEL=claude-haiku-4-5
OPENAI_MODEL=gpt-4
GEMINI_MODEL=gemini-2.5-flash
```

## Database Schema

### Core Tables

- **urls**: URL tracking with SHA-256 hash for O(1) deduplication lookup
- **articles**: Extracted content with metadata (title, author, date, text)
- **ai_analyses**: AI API responses and classifications from Claude, OpenAI, Gemini
- **notifications_sent**: Notification delivery log (Slack, email)
- **host_crawl_state**: Per-domain crawl delays and politeness tracking

### Example Queries

```sql
-- Get AI articles from last 24 hours
SELECT a.title, a.summary, u.url, a.university_name, a.first_scraped
FROM articles a
JOIN urls u ON a.url_id = u.url_id
WHERE a.is_ai_related = TRUE
  AND a.first_scraped >= NOW() - INTERVAL '24 hours'
ORDER BY a.first_scraped DESC;

-- Count articles by university (last week)
SELECT university_name, COUNT(*) as article_count
FROM articles
WHERE is_ai_related = TRUE
  AND first_scraped >= NOW() - INTERVAL '7 days'
GROUP BY university_name
ORDER BY article_count DESC;
```

## Monitoring & Logs

### View Logs

```bash
# Real-time application logs
tail -f logs/crawler.log

# Real-time systemd logs (if using systemd)
journalctl -u ai-news-crawler -f

# Last 100 lines
journalctl -u ai-news-crawler -n 100

# Logs from specific date
journalctl -u ai-news-crawler --since "2025-01-15"
```

### Check Crawler Status

```bash
# Service status
systemctl status ai-news-crawler.service

# Timer status
systemctl status ai-news-crawler.timer

# Next scheduled run
systemctl list-timers --all | grep ai-news-crawler
```

### Database Backups

```bash
# Backup database
pg_dump ai_news_crawler | gzip > backup_$(date +%Y%m%d).sql.gz

# Restore database
gunzip -c backup_20250115.sql.gz | psql ai_news_crawler

# Automated backups (add to crontab)
0 2 * * * pg_dump ai_news_crawler | gzip > /backups/ai_crawler_$(date +\%Y\%m\%d).sql.gz
```

## Cost Estimation

**Estimated monthly costs** (assuming 100 articles/day, ~3000 articles/month):

| Service | Usage | Cost/Month |
|---------|-------|------------|
| Claude Haiku 4.5 | ~3000 requests × 1500 tokens | ~$1.50 |
| OpenAI GPT-4 | ~3000 requests × 1500 tokens | ~$27 |
| Gemini 2.5 Flash | ~3000 requests × 1500 tokens | ~$0.30 |
| **Total** | | **~$29/month** |

### Cost Optimization Strategies

1. **Use Gemini for initial filtering** - Identify AI-related articles with cheap API first
2. **Batch processing** - Process multiple articles per AI call when possible
3. **Token limits** - Set `MAX_AI_TOKENS=500` for summaries
4. **Selective analysis** - Only send high-confidence articles to expensive APIs
5. **Cache results** - Store AI summaries to avoid reprocessing

## Troubleshooting

### Common Issues

**"Database connection failed"**
```bash
# Check PostgreSQL is running
systemctl status postgresql

# Test database connection
psql -U crawler -d ai_news_crawler

# Verify DATABASE_URL in .env file
grep DATABASE_URL .env
```

**"API key invalid"**
```bash
# Test API keys individually
python scripts/test_api_keys.sh

# Check API key format in .env
# Claude: sk-ant-...
# OpenAI: sk-...
# Gemini: alphanumeric string
```

**"No articles found"**
```bash
# Test university URLs are accessible
curl -I https://news.stanford.edu/

# Check crawler logs for errors
tail -100 logs/crawler.log

# Verify MIN_ARTICLE_LENGTH isn't too restrictive
grep MIN_ARTICLE_LENGTH .env
```

**"Notifications not sending"**
```bash
# Test notification configuration
python scripts/test_notifications.py

# For Slack: verify webhook URL format (example format below)
# Format: https://hooks.slack.com/services/YOUR_WORKSPACE_ID/YOUR_CHANNEL_ID/YOUR_TOKEN

# For Email: verify SMTP credentials and App Password (not account password)
```

### Debug Mode

```bash
# Enable detailed logging
export LOG_LEVEL=DEBUG
python -m crawler

# Test single university
python -c "
from crawler.spiders.university_spider import UniversitySpider
from scrapy.crawler import CrawlerProcess

process = CrawlerProcess()
process.crawl(UniversitySpider, start_urls=['https://news.stanford.edu/'])
process.start()
"
```

## Security Best Practices

- Never commit `.env` files (already in `.gitignore`)
- Use Gmail App Passwords for SMTP (not your account password)
- Run systemd service as non-root user
- Set strict file permissions: `chmod 600 .env`
- Rotate API keys every 90 days
- Use read-only database users for reporting queries
- Monitor crawl logs for suspicious activity

## Development

### Running Tests

```bash
# Install dev dependencies
pip install pytest pytest-cov pytest-asyncio

# Run all tests (when implemented)
pytest

# Run with coverage
pytest --cov=crawler tests/
```

### Creating Database Migrations

```bash
# After modifying models.py, create migration
alembic revision --autogenerate -m "Add new field to articles table"

# Review generated migration in alembic/versions/

# Apply migration
alembic upgrade head

# Rollback if needed
alembic downgrade -1
```

### Adding New AI APIs

See `crawler/ai/analyzer.py` for the multi-AI orchestration pattern. To add a new API:

1. Create new client file: `crawler/ai/new_api_client.py`
2. Implement `analyze_article(text: str) -> dict` method
3. Add to parallel processing in `analyzer.py`
4. Add API key to `.env.example`

## Contributing

1. Fork the repository
2. Create feature branch: `git checkout -b feature/amazing-feature`
3. Make changes with clear commit messages
4. Add tests for new functionality
5. Ensure all tests pass: `pytest`
6. Push to branch: `git push origin feature/amazing-feature`
7. Open a Pull Request with detailed description

## License

MIT License - see [LICENSE](LICENSE) file for details.

## Acknowledgments

- **Crawling**: [Scrapy](https://scrapy.org/) - Fast and powerful web scraping framework
- **Extraction**: [Trafilatura](https://trafilatura.readthedocs.io/) - High-quality content extraction
- **AI Analysis**:
  - [Anthropic Claude Haiku](https://www.anthropic.com/) - Fast, cost-effective primary analysis
  - [OpenAI GPT](https://openai.com/) - Secondary validation
  - [Google Gemini](https://deepmind.google/technologies/gemini/) - Additional fast screening
- **Database**: [SQLAlchemy](https://www.sqlalchemy.org/) + [PostgreSQL](https://www.postgresql.org/)
- **Ethics**: Designed for ethical web scraping following [robots.txt](https://www.robotstxt.org/) standards

## Support

- **Issues**: [GitHub Issues](https://github.com/yourusername/ai-news-crawler/issues)
- **Documentation**: See `CLAUDE.md` for detailed architecture documentation
- **Scripts**: Check `scripts/README.md` for utility script documentation

---

**Built with care for ethical AI research tracking** 🤖📰🎓
