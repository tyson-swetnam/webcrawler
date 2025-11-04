#!/bin/bash

# ==============================================================================
# Daily Crawler & GitHub Pages Publisher
# Runs the AI news crawler and publishes results to GitHub Pages
# ==============================================================================

set -e  # Exit on error

# Color codes for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
VENV_DIR="$PROJECT_DIR/venv"
LOG_DIR="$PROJECT_DIR/logs"
LOG_FILE="$LOG_DIR/daily_crawl_$(date +%Y%m%d_%H%M%S).log"
GITHUB_BRANCH="${GITHUB_BRANCH:-website}"  # Default to website branch

# Create logs directory
mkdir -p "$LOG_DIR"

# Logging function
log() {
    echo -e "${BLUE}[$(date +'%Y-%m-%d %H:%M:%S')]${NC} $1" | tee -a "$LOG_FILE"
}

log_success() {
    echo -e "${GREEN}[$(date +'%Y-%m-%d %H:%M:%S')] ✓${NC} $1" | tee -a "$LOG_FILE"
}

log_error() {
    echo -e "${RED}[$(date +'%Y-%m-%d %H:%M:%S')] ✗${NC} $1" | tee -a "$LOG_FILE"
}

log_warning() {
    echo -e "${YELLOW}[$(date +'%Y-%m-%d %H:%M:%S')] ⚠${NC} $1" | tee -a "$LOG_FILE"
}

# Start
log "=========================================================================="
log "Starting Daily AI News Crawler & Publisher"
log "=========================================================================="
log "Project Directory: $PROJECT_DIR"
log "Log File: $LOG_FILE"
log "Branch: $GITHUB_BRANCH"
log ""

# Change to project directory
cd "$PROJECT_DIR"

# Check if virtual environment exists
if [ ! -d "$VENV_DIR" ]; then
    log_error "Virtual environment not found at $VENV_DIR"
    log_error "Please run: python3 -m venv venv && source venv/bin/activate && pip install -r requirements.txt"
    exit 1
fi

# Activate virtual environment
log "Activating virtual environment..."
source "$VENV_DIR/bin/activate"
log_success "Virtual environment activated"

# Verify we're on the correct branch
CURRENT_BRANCH=$(git branch --show-current)
if [ "$CURRENT_BRANCH" != "$GITHUB_BRANCH" ]; then
    log_warning "Currently on branch '$CURRENT_BRANCH', switching to '$GITHUB_BRANCH'..."
    git checkout "$GITHUB_BRANCH" 2>&1 | tee -a "$LOG_FILE"
fi

# Pull latest changes to avoid conflicts
log "Pulling latest changes from origin/$GITHUB_BRANCH..."
git pull origin "$GITHUB_BRANCH" 2>&1 | tee -a "$LOG_FILE" || {
    log_warning "Git pull failed or had conflicts, continuing anyway..."
}

# Check if .env file exists
if [ ! -f "$PROJECT_DIR/.env" ]; then
    log_error ".env file not found! Please create it from .env.example"
    exit 1
fi

# Run the crawler
log ""
log "=========================================================================="
log "Phase 1: Running AI News Crawler"
log "=========================================================================="

python -m crawler 2>&1 | tee -a "$LOG_FILE"
CRAWLER_EXIT_CODE=${PIPESTATUS[0]}

if [ $CRAWLER_EXIT_CODE -ne 0 ]; then
    log_error "Crawler failed with exit code $CRAWLER_EXIT_CODE"
    exit 1
fi

log_success "Crawler completed successfully"

# Check if docs/ folder has changes
log ""
log "=========================================================================="
log "Phase 2: Checking for changes to publish"
log "=========================================================================="

cd "$PROJECT_DIR"

# Check git status for docs/ folder
if git diff --quiet docs/ && git diff --cached --quiet docs/; then
    log_warning "No changes detected in docs/ folder"
    log "Nothing to commit. Exiting."
    exit 0
fi

log_success "Changes detected in docs/ folder"

# Show what changed
log "Changes to be committed:"
git status --short docs/ 2>&1 | tee -a "$LOG_FILE"

# Stage the docs/ folder changes
log ""
log "Staging docs/ folder changes..."
git add docs/ 2>&1 | tee -a "$LOG_FILE"

# Create commit message with date and article count
COMMIT_DATE=$(date +'%Y-%m-%d %H:%M %Z')
ARTICLE_COUNT=$(grep -o "Total Articles:" docs/index.html | wc -l || echo "0")

COMMIT_MSG="Daily crawler update - $COMMIT_DATE

Automated crawl results:
- Updated docs/index.html with latest AI news
- Updated docs/archive/index.html
- Generated on: $COMMIT_DATE

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>"

# Commit changes
log ""
log "Committing changes..."
git commit -m "$COMMIT_MSG" 2>&1 | tee -a "$LOG_FILE"

if [ $? -ne 0 ]; then
    log_error "Git commit failed"
    exit 1
fi

log_success "Changes committed successfully"

# Push to GitHub
log ""
log "=========================================================================="
log "Phase 3: Publishing to GitHub Pages"
log "=========================================================================="

log "Pushing to origin/$GITHUB_BRANCH..."
git push origin "$GITHUB_BRANCH" 2>&1 | tee -a "$LOG_FILE"

if [ $? -ne 0 ]; then
    log_error "Git push failed"
    log_error "You may need to configure git credentials or SSH keys"
    exit 1
fi

log_success "Successfully pushed to GitHub!"

# Summary
log ""
log "=========================================================================="
log "Summary"
log "=========================================================================="
log_success "Daily crawler completed successfully"
log_success "Results published to GitHub Pages"
log "View your site at: https://tyson-swetnam.github.io/webcrawler/"
log "Log file saved to: $LOG_FILE"
log "=========================================================================="

exit 0
