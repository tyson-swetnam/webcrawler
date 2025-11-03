#!/bin/bash
#
# View Latest Results Script
# Displays the most recent crawler results in the terminal
#
# Usage:
#   ./scripts/view_latest_results.sh           # View text summary
#   ./scripts/view_latest_results.sh json      # View JSON results
#   ./scripts/view_latest_results.sh csv       # View CSV results
#   ./scripts/view_latest_results.sh html      # Open HTML report in browser

set -e

# Configuration
OUTPUT_DIR="${OUTPUT_DIR:-./output}"
FORMAT="${1:-text}"

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Print colored header
print_header() {
    echo -e "${BLUE}========================================${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}========================================${NC}"
}

print_success() {
    echo -e "${GREEN}✓${NC} $1"
}

print_error() {
    echo -e "${RED}✗${NC} $1"
}

print_info() {
    echo -e "${YELLOW}ℹ${NC} $1"
}

# Check if output directory exists
if [ ! -d "$OUTPUT_DIR" ]; then
    print_error "Output directory not found: $OUTPUT_DIR"
    echo "Run the crawler first to generate results:"
    echo "  python -m crawler"
    exit 1
fi

# Function to get latest file
get_latest_file() {
    local pattern="$1"
    local latest=$(find "$OUTPUT_DIR" -name "$pattern" -type f -printf '%T@ %p\n' 2>/dev/null | sort -rn | head -1 | cut -d' ' -f2-)
    echo "$latest"
}

# View based on format
case "$FORMAT" in
    text|txt)
        print_header "Latest Text Summary"
        LATEST_FILE=$(get_latest_file "summary_*.txt")

        if [ -z "$LATEST_FILE" ]; then
            print_error "No text summary files found in $OUTPUT_DIR"
            exit 1
        fi

        print_success "File: $LATEST_FILE"
        echo ""
        cat "$LATEST_FILE"
        ;;

    json)
        print_header "Latest JSON Results"
        LATEST_FILE=$(get_latest_file "results_*.json")

        if [ -z "$LATEST_FILE" ]; then
            print_error "No JSON result files found in $OUTPUT_DIR/results/"
            exit 1
        fi

        print_success "File: $LATEST_FILE"
        echo ""

        # Check if jq is available for pretty printing
        if command -v jq &> /dev/null; then
            cat "$LATEST_FILE" | jq '.'
        else
            print_info "Install 'jq' for pretty JSON output: sudo apt install jq"
            cat "$LATEST_FILE"
        fi
        ;;

    csv)
        print_header "Latest CSV Export"
        LATEST_FILE=$(get_latest_file "articles_*.csv")

        if [ -z "$LATEST_FILE" ]; then
            print_error "No CSV export files found in $OUTPUT_DIR/exports/"
            exit 1
        fi

        print_success "File: $LATEST_FILE"
        echo ""

        # Check if column is available for pretty table
        if command -v column &> /dev/null; then
            head -20 "$LATEST_FILE" | column -t -s ','

            # Count total rows
            TOTAL_ROWS=$(($(wc -l < "$LATEST_FILE") - 1))
            if [ $TOTAL_ROWS -gt 19 ]; then
                echo ""
                print_info "Showing first 19 of $TOTAL_ROWS articles"
                echo "View full file: cat $LATEST_FILE"
            fi
        else
            head -20 "$LATEST_FILE"
            print_info "Install 'column' for better formatting"
        fi
        ;;

    html)
        print_header "Opening HTML Report"
        LATEST_FILE=$(get_latest_file "report_*.html")

        if [ -z "$LATEST_FILE" ]; then
            print_error "No HTML report files found in $OUTPUT_DIR/reports/"
            exit 1
        fi

        print_success "File: $LATEST_FILE"

        # Open in browser
        if command -v xdg-open &> /dev/null; then
            xdg-open "$LATEST_FILE"
            print_success "Opened in default browser"
        elif command -v open &> /dev/null; then
            open "$LATEST_FILE"
            print_success "Opened in default browser"
        else
            print_error "Cannot open browser automatically"
            echo "Open manually: file://$LATEST_FILE"
        fi
        ;;

    list|ls)
        print_header "Available Result Files"

        echo -e "\n${YELLOW}Text Summaries:${NC}"
        find "$OUTPUT_DIR" -name "summary_*.txt" -type f -printf '%TY-%Tm-%Td %TH:%TM  %p\n' 2>/dev/null | sort -r | head -5

        echo -e "\n${YELLOW}JSON Results:${NC}"
        find "$OUTPUT_DIR/results" -name "results_*.json" -type f -printf '%TY-%Tm-%Td %TH:%TM  %p\n' 2>/dev/null | sort -r | head -5

        echo -e "\n${YELLOW}CSV Exports:${NC}"
        find "$OUTPUT_DIR/exports" -name "articles_*.csv" -type f -printf '%TY-%Tm-%Td %TH:%TM  %p\n' 2>/dev/null | sort -r | head -5

        echo -e "\n${YELLOW}HTML Reports:${NC}"
        find "$OUTPUT_DIR/reports" -name "report_*.html" -type f -printf '%TY-%Tm-%Td %TH:%TM  %p\n' 2>/dev/null | sort -r | head -5
        ;;

    stats)
        print_header "Crawler Statistics"

        LATEST_JSON=$(get_latest_file "results_*.json")

        if [ -z "$LATEST_JSON" ]; then
            print_error "No result files found"
            exit 1
        fi

        print_success "File: $LATEST_JSON"
        echo ""

        if command -v jq &> /dev/null; then
            echo "Date:           $(jq -r '.date' "$LATEST_JSON")"
            echo "Timestamp:      $(jq -r '.timestamp' "$LATEST_JSON")"
            echo "Article Count:  $(jq -r '.article_count' "$LATEST_JSON")"
            echo ""

            # AI analysis stats
            AI_ENABLED=$(jq -r '.metadata.enable_ai_analysis' "$LATEST_JSON")
            echo "AI Analysis:    $AI_ENABLED"

            if [ "$AI_ENABLED" = "true" ]; then
                ANALYSIS_COUNT=$(jq '.ai_analyses | length' "$LATEST_JSON")
                echo "AI Analyses:    $ANALYSIS_COUNT"
            fi
        else
            cat "$LATEST_JSON"
            print_info "Install 'jq' for better statistics: sudo apt install jq"
        fi
        ;;

    help|--help|-h)
        echo "Usage: $0 [FORMAT]"
        echo ""
        echo "View latest crawler results in different formats"
        echo ""
        echo "Formats:"
        echo "  text    - View text summary (default)"
        echo "  json    - View JSON results"
        echo "  csv     - View CSV export"
        echo "  html    - Open HTML report in browser"
        echo "  list    - List all available result files"
        echo "  stats   - Show crawler statistics"
        echo "  help    - Show this help message"
        echo ""
        echo "Examples:"
        echo "  $0              # View latest text summary"
        echo "  $0 json         # View latest JSON results"
        echo "  $0 html         # Open HTML report"
        echo "  $0 list         # List all files"
        ;;

    *)
        print_error "Unknown format: $FORMAT"
        echo "Use '$0 help' for usage information"
        exit 1
        ;;
esac

echo ""
