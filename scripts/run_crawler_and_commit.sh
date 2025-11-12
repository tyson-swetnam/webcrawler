#!/bin/bash
# Automated crawler execution with git commit/push
# This script is executed by systemd timer

set -e  # Exit on any error

REPO_DIR="/home/tswetnam/github/webcrawler"
VENV_DIR="$REPO_DIR/venv"
DATE=$(date +"%Y-%m-%d %H:%M %Z")

cd "$REPO_DIR"

# Activate virtual environment
source "$VENV_DIR/bin/activate"

# Pull latest changes from remote before running crawler
echo "Pulling latest changes from remote..."
git pull origin website || echo "Warning: git pull failed, continuing anyway..."

# Run the crawler
echo "Running crawler at $DATE..."
python -m crawler

# Check if there are changes to commit
if [[ -n $(git status --porcelain) ]]; then
    echo "Changes detected, committing and pushing..."

    # Stage all changes in docs/ and any updated config files
    git add docs/
    git add crawler/config/*.json 2>/dev/null || true

    # Create commit
    git commit -m "Daily crawler update - $DATE"

    # Pull again in case there were remote changes during crawler execution
    git pull --rebase origin website || {
        echo "Warning: git pull --rebase failed, trying regular push..."
    }

    # Push to remote
    git push origin website || {
        echo "Error: git push failed at $DATE"
        exit 1
    }

    echo "Changes pushed successfully at $DATE"
else
    echo "No changes to commit at $DATE"
fi
