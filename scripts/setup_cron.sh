#!/bin/bash

# ==============================================================================
# Setup Cron Job for Daily Crawler
# Installs a cron job to run the crawler daily at 07:00 PST
# ==============================================================================

set -e

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo "=========================================================================="
echo "  AI News Crawler - Cron Job Setup"
echo "=========================================================================="
echo ""

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
CRAWLER_SCRIPT="$SCRIPT_DIR/daily_crawl_and_publish.sh"

# Verify the crawler script exists
if [ ! -f "$CRAWLER_SCRIPT" ]; then
    echo -e "${RED}Error: Crawler script not found at $CRAWLER_SCRIPT${NC}"
    exit 1
fi

# Make sure it's executable
chmod +x "$CRAWLER_SCRIPT"

echo -e "${BLUE}Project Directory:${NC} $PROJECT_DIR"
echo -e "${BLUE}Crawler Script:${NC} $CRAWLER_SCRIPT"
echo ""

# Ask for confirmation
echo -e "${YELLOW}This will install a cron job to run the crawler daily at 07:00 PST${NC}"
echo ""
echo "The cron job will:"
echo "  1. Run the AI news crawler"
echo "  2. Generate HTML reports in docs/"
echo "  3. Commit changes to git"
echo "  4. Push to GitHub (website branch)"
echo ""

read -p "Continue? (y/n) " -n 1 -r
echo ""

if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Cancelled."
    exit 0
fi

# Create cron job entry
# Runs at 07:00 local time every day
CRON_SCHEDULE="0 7 * * *"
CRON_JOB="$CRON_SCHEDULE cd $PROJECT_DIR && $CRAWLER_SCRIPT >> $PROJECT_DIR/logs/cron.log 2>&1"

# Check if cron job already exists
EXISTING_CRON=$(crontab -l 2>/dev/null | grep -F "$CRAWLER_SCRIPT" || echo "")

if [ -n "$EXISTING_CRON" ]; then
    echo -e "${YELLOW}Existing cron job found:${NC}"
    echo "  $EXISTING_CRON"
    echo ""
    read -p "Remove existing cron job and replace? (y/n) " -n 1 -r
    echo ""

    if [[ $REPLY =~ ^[Yy]$ ]]; then
        # Remove existing job
        crontab -l 2>/dev/null | grep -vF "$CRAWLER_SCRIPT" | crontab -
        echo -e "${GREEN}✓${NC} Removed existing cron job"
    else
        echo "Keeping existing cron job. Exiting."
        exit 0
    fi
fi

# Add new cron job
echo ""
echo "Installing cron job..."
(crontab -l 2>/dev/null; echo "$CRON_JOB") | crontab -

echo -e "${GREEN}✓${NC} Cron job installed successfully!"
echo ""
echo "=========================================================================="
echo "Cron Job Details"
echo "=========================================================================="
echo -e "${BLUE}Schedule:${NC} Daily at 07:00 PST"
echo -e "${BLUE}Command:${NC} $CRAWLER_SCRIPT"
echo -e "${BLUE}Log File:${NC} $PROJECT_DIR/logs/cron.log"
echo ""

# Show current crontab
echo "Current crontab:"
echo "---"
crontab -l | grep -F "$CRAWLER_SCRIPT" || echo "(no matching entries)"
echo "---"
echo ""

# Important notes
echo "=========================================================================="
echo "Important: Git Authentication Setup"
echo "=========================================================================="
echo ""
echo -e "${YELLOW}⚠  For automated git push to work, you need to configure credentials:${NC}"
echo ""
echo "Option 1: SSH Keys (Recommended)"
echo "  1. Generate SSH key: ssh-keygen -t ed25519 -C 'your@email.com'"
echo "  2. Add to GitHub: cat ~/.ssh/id_ed25519.pub"
echo "  3. Go to: https://github.com/settings/keys"
echo "  4. Test: ssh -T git@github.com"
echo ""
echo "Option 2: Git Credential Helper (HTTPS)"
echo "  1. Configure: git config --global credential.helper store"
echo "  2. Run git push once manually to save credentials"
echo ""
echo "Option 3: Personal Access Token"
echo "  1. Create token: https://github.com/settings/tokens"
echo "  2. Store in .git/config or use credential helper"
echo ""
echo "After setting up git authentication, test the script manually:"
echo "  $CRAWLER_SCRIPT"
echo ""
echo "=========================================================================="

# Test git authentication
echo ""
read -p "Test git push authentication now? (y/n) " -n 1 -r
echo ""

if [[ $REPLY =~ ^[Yy]$ ]]; then
    cd "$PROJECT_DIR"
    echo ""
    echo "Testing git authentication..."

    # Try a simple git command that requires authentication
    if git ls-remote origin &>/dev/null; then
        echo -e "${GREEN}✓${NC} Git authentication successful!"
    else
        echo -e "${RED}✗${NC} Git authentication failed"
        echo "Please configure git credentials before the cron job runs"
    fi
fi

echo ""
echo -e "${GREEN}Setup complete!${NC}"
echo ""
echo "To view cron logs:"
echo "  tail -f $PROJECT_DIR/logs/cron.log"
echo ""
echo "To view all cron jobs:"
echo "  crontab -l"
echo ""
echo "To remove this cron job:"
echo "  crontab -e  # then delete the line containing: $CRAWLER_SCRIPT"
echo ""
