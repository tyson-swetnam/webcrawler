# AI University News Crawler

A production-grade Python application that automatically crawls US university news sites for AI-related content, analyzes articles using multiple AI APIs (Claude, OpenAI, Gemini), and delivers intelligent summaries via Slack and email.

## Features

- **Automated Daily Crawling**: Scrapy-based spider crawls 15+ top university news sites
- **High-Quality Content Extraction**: Trafilatura extracts clean article text with 95%+ accuracy
- **Multi-AI Analysis**: Parallel processing with Claude Sonnet-4-5, GPT-4, and Gemini 2.5 Flash
- **Smart Deduplication**: Hash-based URL and content fingerprinting prevents duplicates
- **Dual Notifications**: Formatted reports via Slack webhooks and HTML email
- **Production-Ready**: Systemd timers, database migrations, comprehensive logging
- **Ethical Crawling**: Respects robots.txt, implements rate limiting, configurable delays

## Quick Start

### Prerequisites

- Python 3.11+
- PostgreSQL 15+
- Redis 7+ (optional, for URL frontier)
- API keys for Claude, OpenAI, and Gemini

### Installation

```bash
# Clone repository
git clone https://github.com/yourorg/ai-news-crawler.git
cd ai-news-crawler

# Run automated deployment (requires sudo)
sudo bash scripts/deploy.sh

# Or manual installation:
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Configuration

```bash
# Copy environment template
cp .env.example .env

# Edit with your credentials
nano .env
```

Required configuration:
- `DATABASE_URL`: PostgreSQL connection string
- `ANTHROPIC_API_KEY`: Claude API key ([get here](https://console.anthropic.com/))
- `OPENAI_API_KEY`: OpenAI API key ([get here](https://platform.openai.com/api-keys))
- `GEMINI_API_KEY`: Gemini API key ([get here](https://aistudio.google.com/app/apikey))
- `SLACK_WEBHOOK_URL`: Slack webhook ([create here](https://api.slack.com/messaging/webhooks))
- `EMAIL_FROM`, `EMAIL_TO`, `SMTP_PASSWORD`: Email configuration

### Database Setup

```bash
# Create PostgreSQL database
sudo -u postgres psql
CREATE DATABASE ai_news_crawler;
CREATE USER crawler WITH PASSWORD 'your_password';
GRANT ALL PRIVILEGES ON DATABASE ai_news_crawler TO crawler;
\q

# Run migrations
source venv/bin/activate
alembic upgrade head
```

### Running

```bash
# Manual run
python -m crawler

# Test notifications
python scripts/test_notifications.py

# Enable automatic daily runs (systemd)
sudo systemctl enable ai-news-crawler.timer
sudo systemctl start ai-news-crawler.timer

# Check status
systemctl status ai-news-crawler.timer
systemctl list-timers --all

# View logs
journalctl -u ai-news-crawler -f
```

## Architecture

### Pipeline Phases

1. **Discovery & Crawling**: Scrapy spider identifies new articles from configured universities
2. **Content Extraction**: Trafilatura extracts title, author, date, and clean text
3. **Deduplication**: SHA-256 hashing checks for seen URLs and duplicate content
4. **AI Analysis**: Parallel calls to Claude, OpenAI, and Gemini for classification
5. **Reporting**: Generate formatted summaries and send via Slack + email
6. **Persistence**: Store results in PostgreSQL with full audit trail

### Technology Stack

- **Crawling**: Scrapy 2.11+ with autothrottle and politeness controls
- **Extraction**: Trafilatura 2.0+ for article parsing
- **Database**: PostgreSQL 15+ with SQLAlchemy ORM
- **AI APIs**: Anthropic Claude Sonnet-4-5, OpenAI GPT-4, Google Gemini 2.5 Flash
- **Scheduling**: Systemd timers (or cron)
- **Notifications**: Slack Block Kit + HTML email (SMTP)

## Project Structure

```
ai-news-crawler/
├── crawler/                    # Main application package
│   ├── __main__.py            # Entry point
│   ├── config/                # Configuration
│   │   ├── settings.py        # Pydantic settings
│   │   └── universities.json  # University sources
│   ├── spiders/               # Scrapy spiders
│   │   └── university_spider.py
│   ├── extractors/            # Content extraction
│   │   └── content.py
│   ├── db/                    # Database layer
│   │   ├── models.py          # SQLAlchemy models
│   │   ├── session.py         # Connection pooling
│   │   └── migrations/        # Alembic migrations
│   ├── ai/                    # AI integration
│   │   └── analyzer.py        # Multi-AI orchestration
│   ├── notifiers/             # Notification channels
│   │   ├── slack.py
│   │   └── email.py
│   └── utils/                 # Utilities
│       ├── deduplication.py
│       ├── rate_limiter.py
│       └── report_generator.py
├── deployment/                # Systemd configs
│   ├── ai-news-crawler.service
│   └── ai-news-crawler.timer
├── scripts/                   # Utility scripts
│   ├── deploy.sh
│   └── test_notifications.py
├── requirements.txt
├── alembic.ini
└── .env.example
```

## Configuration Guide

### University Sources

Edit `crawler/config/universities.json` to add/remove universities:

```json
{
  "name": "Stanford University",
  "news_url": "https://news.stanford.edu/ai/",
  "location": "Stanford, CA",
  "focus_areas": ["Machine Learning", "NLP", "Computer Vision"]
}
```

### AI Analysis Settings

Adjust in `.env`:
```bash
# AI Models
CLAUDE_MODEL=claude-sonnet-4-5-20250929
OPENAI_MODEL=gpt-4
GEMINI_MODEL=gemini-2.5-flash

# Performance
AI_ANALYSIS_BATCH_SIZE=5
MAX_ARTICLES_PER_RUN=1000
```

### Crawling Behavior

```bash
# Politeness settings
MAX_CONCURRENT_REQUESTS=8
CRAWL_DELAY=1.0
REQUEST_TIMEOUT=30

# Content filters
MIN_ARTICLE_LENGTH=100
MAX_ARTICLE_AGE_DAYS=30
LOOKBACK_DAYS=1
```

## Database Schema

### Core Tables

- **urls**: URL tracking with hash-based deduplication
- **articles**: Extracted content with metadata
- **ai_analyses**: Results from Claude, OpenAI, and Gemini
- **notifications_sent**: Notification delivery log
- **host_crawl_state**: Per-domain rate limiting

### Key Queries

```sql
-- Get AI articles from last 24 hours
SELECT a.title, a.summary, u.url, a.university_name
FROM articles a
JOIN urls u ON a.url_id = u.url_id
WHERE a.is_ai_related = TRUE
  AND a.first_scraped >= NOW() - INTERVAL '24 hours'
ORDER BY a.first_scraped DESC;
```

## Monitoring & Maintenance

### View Logs

```bash
# Real-time logs
journalctl -u ai-news-crawler -f

# Last 100 lines
journalctl -u ai-news-crawler -n 100

# Logs from today
journalctl -u ai-news-crawler --since today
```

### Check Statistics

```bash
# Timer status
systemctl status ai-news-crawler.timer

# Service status
systemctl status ai-news-crawler.service

# Recent runs
systemctl list-timers --all
```

### Database Backups

```bash
# Backup database
pg_dump ai_news_crawler | gzip > backup_$(date +%Y%m%d).sql.gz

# Restore database
gunzip -c backup_20240115.sql.gz | psql ai_news_crawler
```

## Development

### Running Tests

```bash
# Run all tests
pytest

# Run specific test file
pytest tests/unit/test_ai_analyzer.py

# Run with coverage
pytest --cov=crawler tests/
```

### Adding New Universities

1. Edit `crawler/config/universities.json`
2. Add university entry with `news_url`
3. Test: `python -m crawler`

### Creating Database Migrations

```bash
# Auto-generate migration
alembic revision --autogenerate -m "description"

# Apply migration
alembic upgrade head

# Rollback
alembic downgrade -1
```

## Troubleshooting

### Common Issues

**"Database connection failed"**
- Check PostgreSQL is running: `systemctl status postgresql`
- Verify credentials in `.env` file
- Test connection: `psql -U crawler -d ai_news_crawler`

**"API key invalid"**
- Verify API keys in `.env` are correct
- Check quota/billing for Claude, OpenAI, Gemini
- Test individual APIs manually

**"No articles found"**
- Check university URLs are accessible
- Review `crawler.log` for errors
- Verify `MIN_ARTICLE_LENGTH` isn't too high

**"Slack/Email notifications not sending"**
- Test configuration: `python scripts/test_notifications.py`
- Verify webhook URL (Slack) or SMTP credentials (Email)
- Check firewall allows outbound connections

### Debug Mode

```bash
# Enable debug logging
export DEBUG=true
export LOG_LEVEL=DEBUG
python -m crawler
```

## Cost Optimization

Estimated monthly costs (100 articles/day):
- **Claude Sonnet**: ~$9/month
- **GPT-4**: ~$27/month
- **Gemini Flash**: ~$0.30/month
- **Total**: ~$36/month

Optimization strategies:
1. Use Gemini for initial AI filtering
2. Only analyze confirmed AI articles with expensive APIs
3. Set `MAX_AI_TOKENS` limits
4. Batch articles when possible

## Security Best Practices

- Never commit `.env` files (in `.gitignore`)
- Use app passwords for Gmail SMTP
- Run systemd service as non-root `crawler` user
- Set strict file permissions: `chmod 600 .env`
- Rotate API keys regularly
- Monitor for unusual crawl volumes

## Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/amazing-feature`
3. Commit changes: `git commit -m 'Add amazing feature'`
4. Push to branch: `git push origin feature/amazing-feature`
5. Open a Pull Request

## License

MIT License - see LICENSE file for details

## Support

For issues, questions, or contributions:
- GitHub Issues: https://github.com/yourorg/ai-news-crawler/issues
- Email: support@yourdomain.com

## Acknowledgments

- Built with [Scrapy](https://scrapy.org/), [Trafilatura](https://trafilatura.readthedocs.io/), and [SQLAlchemy](https://www.sqlalchemy.org/)
- AI analysis powered by [Anthropic Claude](https://www.anthropic.com/), [OpenAI GPT](https://openai.com/), and [Google Gemini](https://deepmind.google/technologies/gemini/)
- Designed for ethical web scraping following [robots.txt](https://www.robotstxt.org/) standards
