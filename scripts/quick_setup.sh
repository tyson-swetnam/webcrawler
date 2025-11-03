#!/bin/bash

# ==============================================================================
# Quick Database Setup - Creates database, user, and applies schema
# ==============================================================================

set -e

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

DB_NAME="ai_news_crawler"
DB_USER="crawler"
DB_PASSWORD="${DB_PASSWORD:-}"

# Prompt for password if not set
if [ -z "$DB_PASSWORD" ]; then
    echo "========================================================================"
    echo "  AI News Crawler - Quick Database Setup"
    echo "========================================================================"
    echo ""
    echo -e "${YELLOW}⚠${NC}  Please set DB_PASSWORD environment variable or enter it now:"
    read -sp "Database password for user '$DB_USER': " DB_PASSWORD
    echo ""
    echo ""
else
    echo "========================================================================"
    echo "  AI News Crawler - Quick Database Setup"
    echo "========================================================================"
    echo ""
fi

echo -e "${BLUE}→${NC} Creating database and user..."
echo ""

# Create everything as postgres user
sudo -u postgres psql << EOF
-- Drop if exists (for clean slate)
DROP DATABASE IF EXISTS ${DB_NAME};
DROP USER IF EXISTS ${DB_USER};

-- Create user
CREATE USER ${DB_USER} WITH ENCRYPTED PASSWORD '${DB_PASSWORD}';

-- Create database
CREATE DATABASE ${DB_NAME} OWNER ${DB_USER};

-- Grant privileges
GRANT ALL PRIVILEGES ON DATABASE ${DB_NAME} TO ${DB_USER};

\c ${DB_NAME}

-- Grant schema privileges
GRANT ALL ON SCHEMA public TO ${DB_USER};
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO ${DB_USER};
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO ${DB_USER};

EOF

echo -e "${GREEN}✓${NC} Database and user created!"
echo ""

echo -e "${BLUE}→${NC} Applying schema..."
echo ""

# Apply schema
export PGPASSWORD="${DB_PASSWORD}"
psql -h localhost -U ${DB_USER} -d ${DB_NAME} -f /home/tswetnam/github/webcrawler/scripts/schema.sql

if [ $? -eq 0 ]; then
    echo ""
    echo -e "${GREEN}✓${NC} Schema applied successfully!"
else
    echo ""
    echo -e "${RED}✗${NC} Failed to apply schema"
    exit 1
fi

echo ""
echo -e "${BLUE}→${NC} Testing connection..."
echo ""

# Test connection
if psql -h localhost -U ${DB_USER} -d ${DB_NAME} -c "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='public';" &> /dev/null; then
    TABLE_COUNT=$(psql -h localhost -U ${DB_USER} -d ${DB_NAME} -t -c "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='public';")
    echo -e "${GREEN}✓${NC} Connection successful!"
    echo -e "${GREEN}✓${NC} Found $TABLE_COUNT tables"
else
    echo -e "${RED}✗${NC} Connection test failed"
    unset PGPASSWORD
    exit 1
fi

unset PGPASSWORD

echo ""
echo "========================================================================"
echo -e "${GREEN}Setup Complete!${NC}"
echo "========================================================================"
echo ""
echo "Database Details:"
echo "  Database: ${DB_NAME}"
echo "  User:     ${DB_USER}"
echo "  Password: ${DB_PASSWORD}"
echo ""
echo "Connection String for .env:"
echo ""
echo -e "${BLUE}DATABASE_URL=postgresql://${DB_USER}:${DB_PASSWORD}@localhost:5432/${DB_NAME}${NC}"
echo ""
echo "Test connection:"
echo "  export DB_PASSWORD=\"${DB_PASSWORD}\""
echo "  bash scripts/test_database.sh"
echo ""
