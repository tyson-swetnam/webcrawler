#!/bin/bash

# ==============================================================================
# PostgreSQL Password Reset Script
# ==============================================================================
#
# This script resets the password for the crawler database user
#
# Usage:
#   bash scripts/reset_password.sh
#
# ==============================================================================

set -e

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo "========================================================================"
echo "  PostgreSQL Password Reset for 'crawler' User"
echo "========================================================================"
echo ""

# Configuration
DB_USER="${DB_USER:-crawler}"
DB_PASSWORD="${DB_PASSWORD:-}"

# Get password if not set
if [ -z "$DB_PASSWORD" ]; then
    echo -e "${YELLOW}Enter new password for database user '$DB_USER':${NC}"
    read -s DB_PASSWORD
    echo ""
    echo -e "${YELLOW}Confirm password:${NC}"
    read -s DB_PASSWORD_CONFIRM
    echo ""

    if [ "$DB_PASSWORD" != "$DB_PASSWORD_CONFIRM" ]; then
        echo -e "${RED}✗${NC} Passwords do not match!"
        exit 1
    fi

    # Validate password length
    if [ ${#DB_PASSWORD} -lt 8 ]; then
        echo -e "${RED}✗${NC} Password must be at least 8 characters long!"
        exit 1
    fi
fi

echo -e "${BLUE}→${NC} Resetting password for user '$DB_USER'..."
echo ""

# Reset the password using sudo -u postgres
if sudo -u postgres psql -c "ALTER USER $DB_USER WITH ENCRYPTED PASSWORD '$DB_PASSWORD';" &> /dev/null; then
    echo -e "${GREEN}✓${NC} Password reset successfully!"
else
    echo -e "${RED}✗${NC} Failed to reset password. User may not exist."
    echo ""
    echo -e "${YELLOW}Creating user '$DB_USER'...${NC}"

    if sudo -u postgres psql -c "CREATE USER $DB_USER WITH ENCRYPTED PASSWORD '$DB_PASSWORD';" &> /dev/null; then
        echo -e "${GREEN}✓${NC} User created successfully!"

        # Grant privileges on the database
        if sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE ai_news_crawler TO $DB_USER;" &> /dev/null; then
            echo -e "${GREEN}✓${NC} Privileges granted!"
        fi
    else
        echo -e "${RED}✗${NC} Failed to create user"
        exit 1
    fi
fi

echo ""
echo -e "${BLUE}→${NC} Testing connection..."
echo ""

# Test the connection
export PGPASSWORD="$DB_PASSWORD"
if psql -h localhost -U "$DB_USER" -d ai_news_crawler -c "SELECT 1;" &> /dev/null 2>&1; then
    echo -e "${GREEN}✓${NC} Connection test successful!"
else
    echo -e "${YELLOW}⚠${NC} Connection test failed. You may need to update pg_hba.conf"
    echo ""
    echo "Add this line to /etc/postgresql/16/main/pg_hba.conf:"
    echo ""
    echo "  host    ai_news_crawler    $DB_USER    127.0.0.1/32    scram-sha-256"
    echo ""
    echo "Then reload PostgreSQL:"
    echo "  sudo systemctl reload postgresql"
fi

unset PGPASSWORD

echo ""
echo "========================================================================"
echo -e "${GREEN}Password Reset Complete!${NC}"
echo "========================================================================"
echo ""
echo "Update your .env file with this connection string:"
echo ""
echo -e "${BLUE}DATABASE_URL=postgresql://$DB_USER:$DB_PASSWORD@localhost:5432/ai_news_crawler${NC}"
echo ""
echo "Or manually edit .env:"
echo "  nano /home/tswetnam/github/webcrawler/.env"
echo ""
