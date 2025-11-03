#!/bin/bash

################################################################################
# API Key Validation Script
#
# Tests all three AI API providers (Claude, OpenAI, Gemini) to verify:
# - API keys are valid and properly configured
# - Models are accessible
# - Basic functionality works
#
# Usage:
#   bash scripts/test_api_keys.sh
#   ./scripts/test_api_keys.sh
#
# Exit Codes:
#   0 - All API keys validated successfully
#   1 - One or more API keys failed validation
################################################################################

set -e

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
BOLD='\033[1m'
NC='\033[0m' # No Color

# Project root directory (parent of scripts/)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Change to project root
cd "$PROJECT_ROOT"

################################################################################
# Helper Functions
################################################################################

print_header() {
    echo -e "${BOLD}${BLUE}"
    echo "================================================================================"
    echo "$1"
    echo "================================================================================"
    echo -e "${NC}"
}

print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠ $1${NC}"
}

print_info() {
    echo -e "${BLUE}ℹ $1${NC}"
}

################################################################################
# Pre-flight Checks
################################################################################

print_header "AI News Crawler - API Key Validation"

# Check if .env file exists
if [ ! -f ".env" ]; then
    print_error ".env file not found!"
    echo ""
    print_info "Please create a .env file from the template:"
    echo "  cp .env.example .env"
    echo ""
    print_info "Then configure your API keys in the .env file"
    exit 1
fi

print_success ".env file found"

# Check if virtual environment is activated
if [ -z "$VIRTUAL_ENV" ]; then
    print_warning "Virtual environment not activated"
    print_info "Checking if venv exists..."

    if [ -d "venv" ]; then
        print_info "Virtual environment found at ./venv"
        print_info "Activating virtual environment..."
        source venv/bin/activate
        print_success "Virtual environment activated"
    else
        print_error "No virtual environment found"
        echo ""
        print_info "Please create a virtual environment first:"
        echo "  python3 -m venv venv"
        echo "  source venv/bin/activate"
        echo "  pip install -r requirements.txt"
        exit 1
    fi
else
    print_success "Virtual environment is active: $VIRTUAL_ENV"
fi

# Check if required Python packages are installed
print_info "Verifying required packages..."

REQUIRED_PACKAGES=("anthropic" "openai" "google-genai" "pytest" "pytest-asyncio" "python-dotenv")
MISSING_PACKAGES=()

for package in "${REQUIRED_PACKAGES[@]}"; do
    if ! python -c "import ${package//-/_}" 2>/dev/null; then
        MISSING_PACKAGES+=("$package")
    fi
done

if [ ${#MISSING_PACKAGES[@]} -gt 0 ]; then
    print_error "Missing required packages: ${MISSING_PACKAGES[*]}"
    echo ""
    print_info "Installing missing packages..."
    pip install -q "${MISSING_PACKAGES[@]}"
    print_success "Packages installed"
else
    print_success "All required packages are installed"
fi

echo ""

################################################################################
# Run API Key Tests
################################################################################

print_header "Running API Key Validation Tests"

# Option 1: Run with pytest (more detailed output)
if command -v pytest &> /dev/null; then
    print_info "Running tests with pytest..."
    echo ""

    # Run pytest with verbose output
    if pytest tests/test_api_keys.py -v --tb=short -x 2>&1; then
        TEST_RESULT=0
    else
        TEST_RESULT=$?
    fi
else
    # Option 2: Run directly with Python (fallback)
    print_info "pytest not found, running tests directly..."
    echo ""

    if python tests/test_api_keys.py; then
        TEST_RESULT=0
    else
        TEST_RESULT=$?
    fi
fi

echo ""

################################################################################
# Display Results
################################################################################

if [ $TEST_RESULT -eq 0 ]; then
    print_header "✓ ALL API KEYS VALIDATED SUCCESSFULLY"
    print_success "All three AI providers are working correctly"
    print_success "Claude (Anthropic): OK"
    print_success "OpenAI: OK"
    print_success "Google Gemini: OK"
    echo ""
    print_info "Your AI News Crawler is ready to run!"
    echo ""
else
    print_header "✗ API KEY VALIDATION FAILED"
    print_error "One or more API providers failed validation"
    echo ""
    print_warning "Common Issues and Solutions:"
    echo ""
    echo "  1. Invalid API Key:"
    echo "     - Check if you copied the API key correctly"
    echo "     - Verify the key hasn't expired"
    echo "     - Ensure no extra spaces or quotes"
    echo ""
    echo "  2. Authentication Failed:"
    echo "     Claude:  https://console.anthropic.com/"
    echo "     OpenAI:  https://platform.openai.com/api-keys"
    echo "     Gemini:  https://aistudio.google.com/app/apikey"
    echo ""
    echo "  3. Model Not Found:"
    echo "     - Check if the model name in .env is correct"
    echo "     - Verify your account has access to the model"
    echo "     - Some models require special API access"
    echo ""
    echo "  4. Quota Exceeded:"
    echo "     - Check your account billing status"
    echo "     - Verify you haven't hit rate limits"
    echo "     - Some APIs require payment method on file"
    echo ""
    print_info "Review the error messages above for specific details"
    echo ""
fi

################################################################################
# Additional Diagnostics
################################################################################

if [ $TEST_RESULT -ne 0 ]; then
    echo ""
    print_header "Configuration Check"

    # Show which keys are configured (masked)
    echo "API Keys configured in .env:"

    if grep -q "^ANTHROPIC_API_KEY=" .env; then
        KEY_VALUE=$(grep "^ANTHROPIC_API_KEY=" .env | cut -d'=' -f2)
        if [ -n "$KEY_VALUE" ] && [ "$KEY_VALUE" != "sk-ant-your-key-here" ]; then
            MASKED_KEY="${KEY_VALUE:0:10}...${KEY_VALUE: -4}"
            print_success "ANTHROPIC_API_KEY: $MASKED_KEY"
        else
            print_error "ANTHROPIC_API_KEY: Not set or using placeholder"
        fi
    else
        print_error "ANTHROPIC_API_KEY: Not found in .env"
    fi

    if grep -q "^OPENAI_API_KEY=" .env; then
        KEY_VALUE=$(grep "^OPENAI_API_KEY=" .env | cut -d'=' -f2)
        if [ -n "$KEY_VALUE" ] && [ "$KEY_VALUE" != "sk-your-openai-key-here" ]; then
            MASKED_KEY="${KEY_VALUE:0:10}...${KEY_VALUE: -4}"
            print_success "OPENAI_API_KEY: $MASKED_KEY"
        else
            print_error "OPENAI_API_KEY: Not set or using placeholder"
        fi
    else
        print_error "OPENAI_API_KEY: Not found in .env"
    fi

    if grep -q "^GEMINI_API_KEY=" .env; then
        KEY_VALUE=$(grep "^GEMINI_API_KEY=" .env | cut -d'=' -f2)
        if [ -n "$KEY_VALUE" ] && [ "$KEY_VALUE" != "your-gemini-key-here" ]; then
            MASKED_KEY="${KEY_VALUE:0:10}...${KEY_VALUE: -4}"
            print_success "GEMINI_API_KEY: $MASKED_KEY"
        else
            print_error "GEMINI_API_KEY: Not set or using placeholder"
        fi
    else
        print_error "GEMINI_API_KEY: Not found in .env"
    fi

    echo ""
    echo "Models configured:"
    grep "^CLAUDE_MODEL=" .env | sed 's/^/  /'
    grep "^OPENAI_MODEL=" .env | sed 's/^/  /'
    grep "^GEMINI_MODEL=" .env | sed 's/^/  /'
    echo ""
fi

################################################################################
# Exit
################################################################################

exit $TEST_RESULT
