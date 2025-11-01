# Deployment Checklist

Use this checklist when deploying the AI News Crawler to ensure all components are properly configured.

## Pre-Deployment

- [ ] Python 3.11+ installed
- [ ] PostgreSQL 15+ installed and running
- [ ] Redis 7+ installed (optional)
- [ ] API keys obtained:
  - [ ] Anthropic Claude API key
  - [ ] OpenAI API key
  - [ ] Google Gemini API key
- [ ] Slack webhook URL created
- [ ] Email SMTP credentials ready (app password for Gmail)

## Installation

- [ ] Clone repository
- [ ] Run `sudo bash scripts/deploy.sh` OR manual installation
- [ ] Create `.env` from `.env.example`
- [ ] Fill in all required environment variables in `.env`
- [ ] Verify file permissions: `chmod 600 .env`

## Database Setup

- [ ] PostgreSQL database created: `ai_news_crawler`
- [ ] Database user created with appropriate permissions
- [ ] Connection string in `.env` is correct
- [ ] Run migrations: `alembic upgrade head`
- [ ] Verify tables created: `\dt` in psql

## Configuration Verification

- [ ] Review `crawler/config/universities.json`
- [ ] Adjust crawl settings in `.env` if needed
- [ ] Set appropriate `LOOKBACK_DAYS`
- [ ] Configure `MAX_ARTICLES_PER_RUN`
- [ ] Set `LOG_LEVEL` (INFO for production, DEBUG for testing)

## Testing

- [ ] Test notifications: `python scripts/test_notifications.py`
  - [ ] Slack webhook works
  - [ ] Email delivery works
- [ ] Test manual crawl: `python -m crawler`
  - [ ] Articles discovered
  - [ ] Content extracted
  - [ ] AI analysis completes
  - [ ] Database updated
  - [ ] Notifications sent

## Systemd Setup

- [ ] Service file installed: `/etc/systemd/system/ai-news-crawler.service`
- [ ] Timer file installed: `/etc/systemd/system/ai-news-crawler.timer`
- [ ] Daemon reloaded: `sudo systemctl daemon-reload`
- [ ] Timer enabled: `sudo systemctl enable ai-news-crawler.timer`
- [ ] Timer started: `sudo systemctl start ai-news-crawler.timer`
- [ ] Verify timer is active: `systemctl list-timers --all`

## Security Review

- [ ] `.env` file not committed to git
- [ ] File permissions on `.env`: 600
- [ ] Service runs as non-root user (`crawler`)
- [ ] API keys are valid and active
- [ ] SMTP password is app password (not account password)
- [ ] Database credentials are secure

## Monitoring Setup

- [ ] Log directory created: `/var/log/ai-news-crawler/`
- [ ] Log rotation configured (if using file logging)
- [ ] Can view logs: `journalctl -u ai-news-crawler -f`
- [ ] Dashboard/monitoring tool configured (optional)

## Post-Deployment Verification

- [ ] Wait for first scheduled run (or trigger manually)
- [ ] Check logs for errors: `journalctl -u ai-news-crawler`
- [ ] Verify database has articles: `SELECT COUNT(*) FROM articles;`
- [ ] Confirm notifications received in Slack/email
- [ ] Review AI analysis quality
- [ ] Check API usage/costs

## Weekly Maintenance

- [ ] Review logs for errors
- [ ] Check database size
- [ ] Verify API costs are within budget
- [ ] Confirm notifications are being delivered
- [ ] Review crawl statistics

## Monthly Tasks

- [ ] Backup database
- [ ] Review and update university list
- [ ] Check for package updates
- [ ] Rotate API keys (best practice)
- [ ] Review and archive old logs

## Troubleshooting Commands

```bash
# Check service status
sudo systemctl status ai-news-crawler.service

# Check timer status
sudo systemctl status ai-news-crawler.timer

# View logs
sudo journalctl -u ai-news-crawler -f

# Manual test run
sudo systemctl start ai-news-crawler.service

# Database check
sudo -u postgres psql ai_news_crawler -c "SELECT COUNT(*) FROM articles WHERE first_scraped >= NOW() - INTERVAL '7 days';"

# Test notifications
python scripts/test_notifications.py

# Check API connectivity
python -c "from crawler.ai.analyzer import MultiAIAnalyzer; a = MultiAIAnalyzer(); print('API clients initialized')"
```

## Emergency Contacts

- System Administrator: [YOUR CONTACT]
- Database Administrator: [YOUR CONTACT]
- API Support:
  - Anthropic: https://support.anthropic.com
  - OpenAI: https://help.openai.com
  - Google: https://support.google.com

## Rollback Procedure

If deployment fails:

1. Stop the timer: `sudo systemctl stop ai-news-crawler.timer`
2. Stop the service: `sudo systemctl stop ai-news-crawler.service`
3. Rollback database: `alembic downgrade -1`
4. Restore previous version of code
5. Investigate logs: `journalctl -u ai-news-crawler --since today`

---

**Deployment Date**: _______________
**Deployed By**: _______________
**Version**: 1.0.0
**Notes**: _______________
