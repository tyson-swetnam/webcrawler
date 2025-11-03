#!/bin/bash

# ==============================================================================
# AI News Crawler - PostgreSQL Database Setup Script
# ==============================================================================
#
# This script creates and configures the PostgreSQL database for the AI News
# Crawler application. It is idempotent and can be safely run multiple times.
#
# Features:
# - Checks PostgreSQL installation
# - Creates database and user
# - Applies complete schema with indexes
# - Tests database connectivity
# - Provides clear error messages and guidance
#
# Usage:
#   bash scripts/setup_database.sh
#
# Environment Variables (optional):
#   DB_PASSWORD - Database password (default: prompts user)
#   DB_NAME     - Database name (default: ai_news_crawler)
#   DB_USER     - Database user (default: crawler)
#   SKIP_PROMPTS - Skip confirmation prompts (default: false)
#
# ==============================================================================

set -e  # Exit on error
set -u  # Exit on undefined variable

# ==============================================================================
# CONFIGURATION
# ==============================================================================

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Default values
DB_NAME="${DB_NAME:-ai_news_crawler}"
DB_USER="${DB_USER:-crawler}"
DB_PASSWORD="${DB_PASSWORD:-}"
SKIP_PROMPTS="${SKIP_PROMPTS:-false}"

# Script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCHEMA_FILE="${SCRIPT_DIR}/schema.sql"

# ==============================================================================
# HELPER FUNCTIONS
# ==============================================================================

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_header() {
    echo ""
    echo "========================================================================"
    echo "  $1"
    echo "========================================================================"
    echo ""
}

# ==============================================================================
# PREREQUISITE CHECKS
# ==============================================================================

check_postgresql_installed() {
    log_info "Checking PostgreSQL installation..."

    if ! command -v psql &> /dev/null; then
        log_error "PostgreSQL client (psql) is not installed."
        echo ""
        echo "Installation instructions:"
        echo ""
        echo "Ubuntu/Debian:"
        echo "  sudo apt update"
        echo "  sudo apt install postgresql postgresql-contrib"
        echo ""
        echo "RHEL/CentOS/Fedora:"
        echo "  sudo dnf install postgresql-server postgresql-contrib"
        echo "  sudo postgresql-setup --initdb"
        echo "  sudo systemctl start postgresql"
        echo ""
        echo "macOS (Homebrew):"
        echo "  brew install postgresql@15"
        echo "  brew services start postgresql@15"
        echo ""
        exit 1
    fi

    log_success "PostgreSQL client found"
}

check_postgresql_running() {
    log_info "Checking PostgreSQL service status..."

    if ! sudo systemctl is-active --quiet postgresql 2>/dev/null; then
        log_warning "PostgreSQL service is not running"

        if [[ "$SKIP_PROMPTS" != "true" ]]; then
            read -p "Would you like to start PostgreSQL now? [y/N] " -n 1 -r
            echo
            if [[ $REPLY =~ ^[Yy]$ ]]; then
                sudo systemctl start postgresql
                log_success "PostgreSQL service started"
            else
                log_error "PostgreSQL must be running. Exiting."
                exit 1
            fi
        fi
    else
        log_success "PostgreSQL service is running"
    fi
}

check_schema_file() {
    log_info "Checking for schema file..."

    if [ ! -f "$SCHEMA_FILE" ]; then
        log_error "Schema file not found at: $SCHEMA_FILE"
        echo ""
        echo "Expected location: $SCHEMA_FILE"
        echo "Please ensure the schema.sql file exists in the scripts directory."
        exit 1
    fi

    log_success "Schema file found: $SCHEMA_FILE"
}

check_postgres_permissions() {
    log_info "Checking PostgreSQL permissions..."

    if ! sudo -u postgres psql -c "SELECT 1;" &> /dev/null; then
        log_error "Cannot connect to PostgreSQL as 'postgres' user"
        echo ""
        echo "This script requires access to the 'postgres' superuser account."
        echo "Please ensure you have sudo privileges."
        exit 1
    fi

    log_success "PostgreSQL permissions verified"
}

# ==============================================================================
# DATABASE SETUP FUNCTIONS
# ==============================================================================

get_database_password() {
    if [ -z "$DB_PASSWORD" ]; then
        log_info "Database password not set. Please provide one."
        echo ""

        while true; do
            read -s -p "Enter password for database user '$DB_USER': " PASSWORD1
            echo
            read -s -p "Confirm password: " PASSWORD2
            echo

            if [ "$PASSWORD1" = "$PASSWORD2" ]; then
                if [ ${#PASSWORD1} -lt 8 ]; then
                    log_warning "Password should be at least 8 characters long"
                    continue
                fi
                DB_PASSWORD="$PASSWORD1"
                break
            else
                log_error "Passwords do not match. Please try again."
            fi
        done

        log_success "Password set"
    else
        log_info "Using password from environment variable"
    fi
}

check_database_exists() {
    if sudo -u postgres psql -lqt | cut -d \| -f 1 | grep -qw "$DB_NAME"; then
        return 0  # Database exists
    else
        return 1  # Database does not exist
    fi
}

check_user_exists() {
    if sudo -u postgres psql -tc "SELECT 1 FROM pg_roles WHERE rolname='$DB_USER'" | grep -q 1; then
        return 0  # User exists
    else
        return 1  # User does not exist
    fi
}

create_database_user() {
    log_info "Creating database user '$DB_USER'..."

    if check_user_exists; then
        log_warning "User '$DB_USER' already exists"

        if [[ "$SKIP_PROMPTS" != "true" ]]; then
            read -p "Would you like to update the password? [y/N] " -n 1 -r
            echo
            if [[ $REPLY =~ ^[Yy]$ ]]; then
                sudo -u postgres psql -c "ALTER USER $DB_USER WITH ENCRYPTED PASSWORD '$DB_PASSWORD';" || {
                    log_error "Failed to update user password"
                    exit 1
                }
                log_success "User password updated"
            fi
        fi
    else
        sudo -u postgres psql -c "CREATE USER $DB_USER WITH ENCRYPTED PASSWORD '$DB_PASSWORD';" || {
            log_error "Failed to create database user"
            exit 1
        }
        log_success "User '$DB_USER' created"
    fi
}

create_database() {
    log_info "Creating database '$DB_NAME'..."

    if check_database_exists; then
        log_warning "Database '$DB_NAME' already exists"

        if [[ "$SKIP_PROMPTS" != "true" ]]; then
            echo ""
            log_warning "Recreating the database will DELETE ALL EXISTING DATA!"
            read -p "Would you like to drop and recreate the database? [y/N] " -n 1 -r
            echo
            if [[ $REPLY =~ ^[Yy]$ ]]; then
                log_info "Dropping existing database..."
                sudo -u postgres psql -c "DROP DATABASE $DB_NAME;" || {
                    log_error "Failed to drop database. Make sure no connections are active."
                    exit 1
                }

                sudo -u postgres psql -c "CREATE DATABASE $DB_NAME OWNER $DB_USER;" || {
                    log_error "Failed to create database"
                    exit 1
                }
                log_success "Database recreated"
            else
                log_info "Keeping existing database"
            fi
        else
            log_info "Database already exists, skipping creation"
        fi
    else
        sudo -u postgres psql -c "CREATE DATABASE $DB_NAME OWNER $DB_USER;" || {
            log_error "Failed to create database"
            exit 1
        }
        log_success "Database '$DB_NAME' created"
    fi
}

grant_privileges() {
    log_info "Granting privileges to user '$DB_USER'..."

    sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE $DB_NAME TO $DB_USER;" || {
        log_error "Failed to grant privileges"
        exit 1
    }

    # Grant schema privileges
    sudo -u postgres psql -d "$DB_NAME" -c "GRANT ALL ON SCHEMA public TO $DB_USER;" || {
        log_warning "Could not grant schema privileges (this is usually OK for new databases)"
    }

    log_success "Privileges granted"
}

apply_schema() {
    log_info "Applying database schema from $SCHEMA_FILE..."

    # Apply schema as the database user (pipe through stdin to avoid permission issues)
    cat "$SCHEMA_FILE" | sudo -u postgres psql -d "$DB_NAME" || {
        log_error "Failed to apply schema"
        exit 1
    }

    log_success "Schema applied successfully"
}

verify_schema() {
    log_info "Verifying schema installation..."

    # Check for expected tables
    local expected_tables=("urls" "articles" "ai_analyses" "notifications_sent" "host_crawl_state")
    local missing_tables=()

    for table in "${expected_tables[@]}"; do
        if ! sudo -u postgres psql -d "$DB_NAME" -tc "SELECT 1 FROM information_schema.tables WHERE table_name='$table'" | grep -q 1; then
            missing_tables+=("$table")
        fi
    done

    if [ ${#missing_tables[@]} -ne 0 ]; then
        log_error "Missing tables: ${missing_tables[*]}"
        exit 1
    fi

    log_success "All expected tables created"
}

test_connection() {
    log_info "Testing database connection..."

    # Create connection string
    export PGPASSWORD="$DB_PASSWORD"

    if psql -h localhost -U "$DB_USER" -d "$DB_NAME" -c "SELECT 1;" &> /dev/null; then
        log_success "Connection test successful"
    else
        log_error "Connection test failed"
        echo ""
        echo "Troubleshooting:"
        echo "1. Check PostgreSQL authentication settings in pg_hba.conf"
        echo "2. Ensure PostgreSQL is configured to accept local connections"
        echo "3. Verify the password is correct"
        echo ""
        echo "Default pg_hba.conf location:"
        echo "  Ubuntu/Debian: /etc/postgresql/15/main/pg_hba.conf"
        echo "  RHEL/CentOS: /var/lib/pgsql/15/data/pg_hba.conf"
        echo ""
        echo "Recommended pg_hba.conf entry:"
        echo "  local   all   $DB_USER   scram-sha-256"
        echo "  host    all   $DB_USER   127.0.0.1/32   scram-sha-256"
        exit 1
    fi

    unset PGPASSWORD
}

generate_connection_string() {
    log_info "Generating connection string for .env file..."

    local connection_string="postgresql://${DB_USER}:${DB_PASSWORD}@localhost:5432/${DB_NAME}"

    echo ""
    echo "========================================================================"
    echo "  Connection String"
    echo "========================================================================"
    echo ""
    echo "Add this to your .env file:"
    echo ""
    echo "DATABASE_URL=${connection_string}"
    echo ""
    echo "========================================================================"
    echo ""
}

print_summary() {
    echo ""
    echo "========================================================================"
    echo "  Database Setup Summary"
    echo "========================================================================"
    echo ""
    echo "Database Name:     $DB_NAME"
    echo "Database User:     $DB_USER"
    echo "Host:              localhost"
    echo "Port:              5432"
    echo ""
    echo "Tables Created:"
    echo "  - urls (URL tracking and deduplication)"
    echo "  - articles (Extracted content)"
    echo "  - ai_analyses (AI API results)"
    echo "  - notifications_sent (Notification log)"
    echo "  - host_crawl_state (Politeness tracking)"
    echo ""
    echo "Indexes Created:"
    echo "  - Hash-based deduplication indexes"
    echo "  - Date and status indexes for queries"
    echo "  - JSONB GIN index for metadata"
    echo ""
    echo "========================================================================"
    echo ""
}

print_next_steps() {
    echo "Next Steps:"
    echo ""
    echo "1. Add the DATABASE_URL to your .env file (see above)"
    echo ""
    echo "2. Verify the connection:"
    echo "   psql -h localhost -U $DB_USER -d $DB_NAME"
    echo ""
    echo "3. If using Alembic migrations, you may want to run:"
    echo "   alembic stamp head"
    echo ""
    echo "4. Test the application:"
    echo "   python -m crawler"
    echo ""
    echo "5. (Optional) Create a database backup:"
    echo "   pg_dump $DB_NAME > backup.sql"
    echo ""
    log_success "Database setup complete!"
    echo ""
}

# ==============================================================================
# MAIN EXECUTION
# ==============================================================================

main() {
    print_header "AI News Crawler - Database Setup"

    log_info "Configuration:"
    echo "  Database: $DB_NAME"
    echo "  User:     $DB_USER"
    echo ""

    # Run prerequisite checks
    check_postgresql_installed
    check_postgresql_running
    check_schema_file
    check_postgres_permissions

    # Get password if not set
    get_database_password

    # Confirm before proceeding
    if [[ "$SKIP_PROMPTS" != "true" ]]; then
        echo ""
        read -p "Proceed with database setup? [Y/n] " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Nn]$ ]]; then
            log_info "Setup cancelled by user"
            exit 0
        fi
    fi

    echo ""
    print_header "Creating Database and User"

    # Create user and database
    create_database_user
    create_database
    grant_privileges

    echo ""
    print_header "Applying Schema"

    # Apply schema
    apply_schema
    verify_schema

    echo ""
    print_header "Testing Connection"

    # Test connection
    test_connection

    # Print results
    generate_connection_string
    print_summary
    print_next_steps
}

# Run main function
main "$@"
