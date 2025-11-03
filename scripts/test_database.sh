#!/bin/bash

# ==============================================================================
# AI News Crawler - Database Connection Test Script
# ==============================================================================
#
# This script tests the database connection and verifies the schema.
#
# Usage:
#   bash scripts/test_database.sh
#
# Environment Variables:
#   DATABASE_URL - Full connection string (optional)
#   DB_NAME      - Database name (default: ai_news_crawler)
#   DB_USER      - Database user (default: crawler)
#   DB_PASSWORD  - Database password (will prompt if not set)
#
# ==============================================================================

set -e

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Configuration
DB_NAME="${DB_NAME:-ai_news_crawler}"
DB_USER="${DB_USER:-crawler}"
DB_PASSWORD="${DB_PASSWORD:-}"

echo "========================================================================"
echo "  AI News Crawler - Database Connection Test"
echo "========================================================================"
echo ""

# Get password if not set
if [ -z "$DB_PASSWORD" ]; then
    read -s -p "Enter password for database user '$DB_USER': " DB_PASSWORD
    echo ""
fi

export PGPASSWORD="$DB_PASSWORD"

echo "Testing connection to database '$DB_NAME' as user '$DB_USER'..."
echo ""

# Test basic connection
if psql -h localhost -U "$DB_USER" -d "$DB_NAME" -c "SELECT 1;" &> /dev/null; then
    echo -e "${GREEN}✓${NC} Connection successful"
else
    echo -e "${RED}✗${NC} Connection failed"
    exit 1
fi

# Check tables
echo ""
echo "Checking database schema..."
echo ""

TABLES=("urls" "articles" "ai_analyses" "notifications_sent" "host_crawl_state")

for table in "${TABLES[@]}"; do
    COUNT=$(psql -h localhost -U "$DB_USER" -d "$DB_NAME" -t -c "SELECT COUNT(*) FROM information_schema.tables WHERE table_name='$table';")
    if [ "$COUNT" -eq 1 ]; then
        echo -e "${GREEN}✓${NC} Table '$table' exists"
    else
        echo -e "${RED}✗${NC} Table '$table' missing"
    fi
done

echo ""
echo "Checking indexes..."
echo ""

# Count indexes
INDEX_COUNT=$(psql -h localhost -U "$DB_USER" -d "$DB_NAME" -t -c "
    SELECT COUNT(*)
    FROM pg_indexes
    WHERE schemaname = 'public';
")

echo -e "${GREEN}✓${NC} Found $INDEX_COUNT indexes"

echo ""
echo "Getting table statistics..."
echo ""

psql -h localhost -U "$DB_USER" -d "$DB_NAME" -c "
SELECT
    relname AS \"Table\",
    pg_size_pretty(pg_total_relation_size(schemaname||'.'||relname)) AS \"Size\",
    n_live_tup AS \"Rows\"
FROM pg_stat_user_tables
ORDER BY relname;
"

echo ""
echo "========================================================================"
echo -e "${GREEN}✓${NC} Database test completed successfully!"
echo "========================================================================"
echo ""

unset PGPASSWORD
