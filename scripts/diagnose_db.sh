#!/bin/bash

# ==============================================================================
# Database Diagnostic Script
# ==============================================================================

set -e

echo "=========================================================================="
echo "  PostgreSQL Database Diagnostics"
echo "=========================================================================="
echo ""

# Check PostgreSQL service
echo "1. Checking PostgreSQL service status..."
systemctl is-active postgresql && echo "   ✓ PostgreSQL is running" || echo "   ✗ PostgreSQL is not running"
echo ""

# Check if we can connect as postgres user
echo "2. Checking database and user existence..."
echo "   (This requires sudo/postgres access)"
echo ""

sudo -u postgres psql -c "\l" | grep -E "ai_news_crawler|Name" || echo "   Database 'ai_news_crawler' not found"
echo ""

sudo -u postgres psql -c "\du" | grep -E "crawler|Role name" || echo "   User 'crawler' not found"
echo ""

# Check pg_hba.conf
echo "3. Checking authentication configuration..."
PG_VERSION=$(psql --version | grep -oP '\d+' | head -1)
PG_HBA_PATH="/etc/postgresql/${PG_VERSION}/main/pg_hba.conf"

if [ -f "$PG_HBA_PATH" ]; then
    echo "   Found pg_hba.conf at: $PG_HBA_PATH"
    echo "   Current authentication rules for local connections:"
    sudo grep -E "^(local|host)" "$PG_HBA_PATH" | grep -v "^#" || echo "   No rules found"
else
    echo "   ✗ Could not find pg_hba.conf"
fi

echo ""
echo "4. Testing connection with password..."

# Get password from environment or prompt
if [ -z "$DB_PASSWORD" ]; then
    read -sp "Enter password for database user 'crawler': " DB_PASSWORD
    echo ""
fi

export PGPASSWORD="$DB_PASSWORD"
if psql -h localhost -U crawler -d ai_news_crawler -c "SELECT 1;" &> /dev/null; then
    echo "   ✓ Connection successful!"
else
    echo "   ✗ Connection failed"
    echo ""
    echo "   Trying detailed connection attempt..."
    psql -h localhost -U crawler -d ai_news_crawler -c "SELECT 1;" 2>&1 | head -10
fi

unset PGPASSWORD
unset DB_PASSWORD

echo ""
echo "=========================================================================="
echo "Diagnostics complete"
echo "=========================================================================="
