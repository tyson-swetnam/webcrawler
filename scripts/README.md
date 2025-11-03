# AI News Crawler Scripts

This directory contains scripts for setting up and managing the AI News Crawler, including database setup, API key validation, and testing utilities.

## Quick Start

```bash
# 1. Validate your AI API keys
bash scripts/test_api_keys.sh

# 2. Run the automated database setup
bash scripts/setup_database.sh
```

## Files

### `test_api_keys.sh`
Comprehensive API key validation script that tests all three AI providers (Claude, OpenAI, Gemini).

**Features:**
- Validates API key format before making API calls
- Tests actual API connectivity with minimal requests
- Provides color-coded success/failure output
- Detects common issues (invalid keys, model access, rate limits, quota)
- Offers actionable next steps for any failures
- Auto-activates virtual environment if needed
- Installs missing dependencies automatically

**Usage:**

```bash
# Run API key validation
bash scripts/test_api_keys.sh

# Or use pytest directly for detailed output
pytest tests/test_api_keys.py -v

# Or run the Python script directly
python tests/test_api_keys.py
```

**Exit Codes:**
- `0` - All API keys validated successfully
- `1` - One or more API keys failed validation

**What it validates:**
- Claude (Anthropic): API key, model access (claude-haiku-4-5)
- OpenAI: API key, model access (gpt-4 or gpt-5-nano)
- Google Gemini: API key, model access (gemini-2.5-flash)

**Output Example:**

```
================================================================================
✓ ALL API KEYS VALIDATED SUCCESSFULLY
================================================================================
✓ All three AI providers are working correctly
✓ Claude (Anthropic): OK
✓ OpenAI: OK
✓ Google Gemini: OK

ℹ Your AI News Crawler is ready to run!
```

**Common Issues and Solutions:**

1. **Invalid API Key Format**
   - Check if you copied the API key correctly from the provider's dashboard
   - Ensure no extra spaces or quotes in the .env file
   - Anthropic keys start with `sk-ant-`
   - OpenAI keys start with `sk-`

2. **Authentication Failed**
   - Verify your API key hasn't expired
   - Check if the key has been revoked
   - Get new keys from:
     - Claude: https://console.anthropic.com/
     - OpenAI: https://platform.openai.com/api-keys
     - Gemini: https://aistudio.google.com/app/apikey

3. **Model Not Found**
   - Verify the model name in .env matches available models
   - Check if your account has access to the specified model
   - Some models require special API access or higher tier plans

4. **Quota Exceeded**
   - Check your account billing status
   - Verify payment method is on file
   - Review usage limits for free tier accounts

## Database Setup Files

### `setup_database.sh`
The main database installation script. It is **idempotent** and can be run multiple times safely.

**Features:**
- Interactive prompts for database password
- Checks all prerequisites (PostgreSQL installation, service status)
- Creates database and user with proper permissions
- Applies complete schema with indexes
- Verifies installation
- Tests database connectivity
- Provides connection string for `.env` file

**Usage:**

```bash
# Interactive mode (recommended for first-time setup)
bash scripts/setup_database.sh

# Non-interactive mode with environment variables
DB_PASSWORD="your_secure_password" bash scripts/setup_database.sh

# Skip all prompts (for automation)
DB_PASSWORD="your_secure_password" SKIP_PROMPTS=true bash scripts/setup_database.sh
```

**Environment Variables:**

- `DB_NAME` - Database name (default: `ai_news_crawler`)
- `DB_USER` - Database user (default: `crawler`)
- `DB_PASSWORD` - Database password (default: prompts user)
- `SKIP_PROMPTS` - Skip confirmation prompts (default: `false`)

**Examples:**

```bash
# Custom database name and user
DB_NAME="my_crawler" DB_USER="myuser" bash scripts/setup_database.sh

# Automated setup for CI/CD
DB_PASSWORD="SecurePass123!" SKIP_PROMPTS=true bash scripts/setup_database.sh
```

### `schema.sql`
The complete PostgreSQL database schema including:

- **5 tables:** urls, articles, ai_analyses, notifications_sent, host_crawl_state
- **11 indexes:** Optimized for common query patterns
- **Constraints:** Data validation and foreign key relationships
- **Extensions:** pgcrypto for advanced hashing

This file can be applied manually:

```bash
psql -U crawler -d ai_news_crawler -f scripts/schema.sql
```

## Database Schema Overview

### Tables

1. **urls** - URL tracking and deduplication
   - Uses SHA-256 hashing for O(1) duplicate detection
   - Tracks crawl status and retry logic
   - Stores content hash to detect article updates

2. **articles** - Extracted article content
   - Stores title, author, content, and metadata
   - AI classification (is_ai_related, confidence score)
   - JSONB field for flexible metadata storage

3. **ai_analyses** - AI API analysis results
   - Stores results from Claude, OpenAI, and Gemini
   - Consensus summary and relevance scoring
   - Processing time tracking

4. **notifications_sent** - Notification delivery log
   - Tracks Slack and email notifications
   - Records recipients and delivery status

5. **host_crawl_state** - Politeness tracking
   - Per-domain crawl delays
   - Robots.txt compliance
   - Temporary blocking support

### Key Indexes

- Hash-based indexes for fast URL deduplication
- Date indexes for recent article queries
- Status indexes for crawl management
- GIN index for JSONB metadata searches

## Troubleshooting

### PostgreSQL Not Running

```bash
# Start PostgreSQL service
sudo systemctl start postgresql

# Enable PostgreSQL to start on boot
sudo systemctl enable postgresql

# Check status
systemctl status postgresql
```

### Connection Failed After Setup

The most common issue is PostgreSQL authentication configuration. Edit `pg_hba.conf`:

```bash
# Find pg_hba.conf location
sudo -u postgres psql -c "SHOW hba_file;"

# Edit the file
sudo nano /etc/postgresql/15/main/pg_hba.conf
```

Add these lines (before the default entries):

```
# AI News Crawler
local   ai_news_crawler   crawler   scram-sha-256
host    ai_news_crawler   crawler   127.0.0.1/32   scram-sha-256
```

Reload PostgreSQL:

```bash
sudo systemctl reload postgresql
```

### Permission Denied

Ensure you have sudo privileges:

```bash
sudo -u postgres psql -c "SELECT 1;"
```

### Database Already Exists

The script will detect existing databases and prompt you before dropping/recreating. You can safely run the script multiple times.

## Manual Setup

If you prefer manual setup or the script fails:

```bash
# 1. Connect to PostgreSQL
sudo -u postgres psql

# 2. Create database and user
CREATE DATABASE ai_news_crawler;
CREATE USER crawler WITH ENCRYPTED PASSWORD 'your_password';
GRANT ALL PRIVILEGES ON DATABASE ai_news_crawler TO crawler;
\q

# 3. Apply schema
psql -U crawler -d ai_news_crawler -f scripts/schema.sql

# 4. Test connection
psql -U crawler -d ai_news_crawler -c "SELECT COUNT(*) FROM urls;"
```

## Backup and Restore

### Create Backup

```bash
# Full database backup
pg_dump ai_news_crawler > backup_$(date +%Y%m%d).sql

# Compressed backup
pg_dump ai_news_crawler | gzip > backup_$(date +%Y%m%d).sql.gz

# Schema only
pg_dump --schema-only ai_news_crawler > schema_backup.sql
```

### Restore Backup

```bash
# Restore from backup
psql -U crawler -d ai_news_crawler < backup_20251031.sql

# Restore from compressed backup
gunzip -c backup_20251031.sql.gz | psql -U crawler -d ai_news_crawler
```

## Database Maintenance

### Check Database Size

```bash
psql -U crawler -d ai_news_crawler -c "
  SELECT pg_size_pretty(pg_database_size('ai_news_crawler'));
"
```

### Vacuum and Analyze

```bash
# Regular maintenance
psql -U crawler -d ai_news_crawler -c "VACUUM ANALYZE;"

# Full vacuum (reclaims space)
psql -U crawler -d ai_news_crawler -c "VACUUM FULL;"
```

### View Table Statistics

```bash
psql -U crawler -d ai_news_crawler -c "
  SELECT
    schemaname,
    tablename,
    pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) AS size,
    n_live_tup AS rows
  FROM pg_stat_user_tables
  ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;
"
```

## Security Best Practices

1. **Use strong passwords** (minimum 12 characters, mixed case, numbers, symbols)
2. **Never commit `.env` files** containing database credentials
3. **Restrict network access** (use firewall rules if database is remote)
4. **Regular backups** (automate with cron)
5. **Monitor logs** for unusual activity
6. **Use SSL/TLS** for remote connections
7. **Keep PostgreSQL updated** with security patches

## Additional Resources

- [PostgreSQL Documentation](https://www.postgresql.org/docs/)
- [PostgreSQL Security Checklist](https://www.postgresql.org/docs/current/auth-pg-hba-conf.html)
- [Tuning PostgreSQL](https://wiki.postgresql.org/wiki/Tuning_Your_PostgreSQL_Server)

## Support

If you encounter issues:

1. Check the error messages carefully
2. Review PostgreSQL logs: `sudo journalctl -u postgresql -n 50`
3. Verify PostgreSQL version: `psql --version` (15+ required)
4. Ensure sufficient disk space: `df -h`
5. Check PostgreSQL configuration: `sudo -u postgres psql -c "SHOW config_file;"`

For project-specific questions, refer to the main README.md or CLAUDE.md files.
