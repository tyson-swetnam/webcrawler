#!/bin/bash

################################################################################
# AI News Crawler - Run with Logging
#
# This script runs the crawler while capturing stdout and stderr to log files
#
# Usage:
#   bash scripts/run_crawler_with_logs.sh
#   ./scripts/run_crawler_with_logs.sh
#
# Logs are saved to:
#   - logs/run_TIMESTAMP_stdout.log - Standard output
#   - logs/run_TIMESTAMP_stderr.log - Standard error
#   - logs/crawler.log - Application logs (from logging config)
################################################################################

set -e

# Color codes
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

# Get script directory and project root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Change to project root
cd "$PROJECT_ROOT"

# Create logs directory if it doesn't exist
mkdir -p logs

# Generate timestamp for this run
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
STDOUT_LOG="logs/run_${TIMESTAMP}_stdout.log"
STDERR_LOG="logs/run_${TIMESTAMP}_stderr.log"

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}AI News Crawler - Starting${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""
echo -e "${GREEN}✓${NC} Timestamp: $TIMESTAMP"
echo -e "${GREEN}✓${NC} Logs directory: $(pwd)/logs"
echo -e "${GREEN}✓${NC} STDOUT log: $STDOUT_LOG"
echo -e "${GREEN}✓${NC} STDERR log: $STDERR_LOG"
echo -e "${GREEN}✓${NC} Application log: logs/crawler.log"
echo ""

# Check if virtual environment is activated
if [ -z "$VIRTUAL_ENV" ]; then
    echo -e "${YELLOW}⚠${NC} Virtual environment not activated"
    if [ -d "venv" ]; then
        echo -e "${BLUE}ℹ${NC} Activating virtual environment..."
        source venv/bin/activate
        echo -e "${GREEN}✓${NC} Virtual environment activated"
    else
        echo -e "${RED}✗${NC} Virtual environment not found at ./venv"
        echo -e "${YELLOW}ℹ${NC} Create one with: python3 -m venv venv"
        exit 1
    fi
fi
echo ""

# Display environment info
echo -e "${BLUE}Environment:${NC}"
echo "  Python: $(python --version 2>&1)"
echo "  Working directory: $(pwd)"
echo "  Virtual env: $VIRTUAL_ENV"
echo ""

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}Starting crawler...${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# Run the crawler with output redirection
# Both stdout and stderr are shown in terminal AND saved to files
python -m crawler 2> >(tee "$STDERR_LOG" >&2) | tee "$STDOUT_LOG"

EXIT_CODE=$?

echo ""
echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}Crawler Finished${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

if [ $EXIT_CODE -eq 0 ]; then
    echo -e "${GREEN}✓${NC} Exit code: $EXIT_CODE (success)"
else
    echo -e "${RED}✗${NC} Exit code: $EXIT_CODE (failure)"
fi

echo ""
echo -e "${BLUE}Log files created:${NC}"
echo "  - $STDOUT_LOG ($(wc -l < "$STDOUT_LOG" 2>/dev/null || echo 0) lines)"
echo "  - $STDERR_LOG ($(wc -l < "$STDERR_LOG" 2>/dev/null || echo 0) lines)"

if [ -f "logs/crawler.log" ]; then
    echo "  - logs/crawler.log ($(wc -l < logs/crawler.log) lines)"
fi

if [ -f "logs/error.log" ]; then
    ERROR_LINES=$(wc -l < logs/error.log)
    if [ "$ERROR_LINES" -gt 0 ]; then
        echo -e "  - logs/error.log (${RED}$ERROR_LINES lines${NC})"
    fi
fi

echo ""
echo -e "${BLUE}View logs:${NC}"
echo "  tail -f logs/crawler.log          # Follow application log"
echo "  tail -f $STDOUT_LOG               # Follow stdout"
echo "  cat $STDERR_LOG                   # View errors"
echo ""

exit $EXIT_CODE
