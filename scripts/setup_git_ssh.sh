#!/bin/bash

# ==============================================================================
# Setup Git SSH Authentication
# Switches repository to SSH for automated cron job authentication
# ==============================================================================

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo "=========================================================================="
echo "  Git SSH Authentication Setup"
echo "=========================================================================="
echo ""

# Check current remote
CURRENT_REMOTE=$(git remote get-url origin)
echo -e "${BLUE}Current remote URL:${NC} $CURRENT_REMOTE"
echo ""

# Check if already using SSH
if [[ $CURRENT_REMOTE == git@github.com:* ]]; then
    echo -e "${GREEN}✓${NC} Already using SSH authentication"
    echo "No changes needed."
    exit 0
fi

# Extract repo path
if [[ $CURRENT_REMOTE == https://github.com/* ]]; then
    REPO_PATH="${CURRENT_REMOTE#https://github.com/}"
    REPO_PATH="${REPO_PATH%.git}"
    SSH_URL="git@github.com:$REPO_PATH.git"
else
    echo -e "${RED}Error: Unable to parse GitHub URL${NC}"
    exit 1
fi

echo "Proposed SSH URL: $SSH_URL"
echo ""

# Check if SSH key exists
echo "Checking for SSH keys..."
if [ ! -f ~/.ssh/id_rsa ] && [ ! -f ~/.ssh/id_ed25519 ]; then
    echo -e "${YELLOW}⚠  No SSH key found${NC}"
    echo ""
    echo "To generate an SSH key:"
    echo "  1. Run: ssh-keygen -t ed25519 -C 'your-email@example.com'"
    echo "  2. Press Enter to accept default location"
    echo "  3. Enter a passphrase (optional but recommended)"
    echo ""

    read -p "Generate SSH key now? (y/n) " -n 1 -r
    echo ""

    if [[ $REPLY =~ ^[Yy]$ ]]; then
        read -p "Enter your email: " user_email
        ssh-keygen -t ed25519 -C "$user_email"

        if [ $? -eq 0 ]; then
            echo -e "${GREEN}✓${NC} SSH key generated successfully"
        else
            echo -e "${RED}✗${NC} SSH key generation failed"
            exit 1
        fi
    else
        echo "Please generate an SSH key and run this script again"
        exit 0
    fi
fi

# Find SSH public key
if [ -f ~/.ssh/id_ed25519.pub ]; then
    SSH_KEY_FILE=~/.ssh/id_ed25519.pub
elif [ -f ~/.ssh/id_rsa.pub ]; then
    SSH_KEY_FILE=~/.ssh/id_rsa.pub
else
    echo -e "${RED}Error: No SSH public key found${NC}"
    exit 1
fi

echo ""
echo -e "${GREEN}✓${NC} Found SSH key: $SSH_KEY_FILE"
echo ""

# Display public key
echo "=========================================================================="
echo "Add this SSH key to GitHub:"
echo "=========================================================================="
echo ""
cat "$SSH_KEY_FILE"
echo ""
echo "1. Copy the key above"
echo "2. Go to: https://github.com/settings/ssh/new"
echo "3. Paste the key and give it a title (e.g., 'webcrawler-server')"
echo "4. Click 'Add SSH key'"
echo ""

read -p "Press Enter after adding the key to GitHub..."

# Test SSH connection
echo ""
echo "Testing SSH connection to GitHub..."
ssh -T git@github.com 2>&1 | grep -q "successfully authenticated"

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓${NC} SSH authentication successful!"
else
    echo -e "${YELLOW}⚠${NC} SSH authentication test inconclusive"
    echo "If you see 'Hi <username>!' above, authentication is working"
    echo ""
    read -p "Continue anyway? (y/n) " -n 1 -r
    echo ""

    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Cancelled. Please add your SSH key to GitHub and try again."
        exit 0
    fi
fi

# Switch remote to SSH
echo ""
echo "Switching remote URL to SSH..."
git remote set-url origin "$SSH_URL"

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓${NC} Remote URL updated to: $SSH_URL"
else
    echo -e "${RED}✗${NC} Failed to update remote URL"
    exit 1
fi

# Verify
UPDATED_REMOTE=$(git remote get-url origin)
echo ""
echo "Verification:"
echo "  Old URL: $CURRENT_REMOTE"
echo "  New URL: $UPDATED_REMOTE"
echo ""

# Test push/pull
echo "Testing git connection..."
if git ls-remote origin &>/dev/null; then
    echo -e "${GREEN}✓${NC} Git connection successful!"
    echo ""
    echo "=========================================================================="
    echo "Setup Complete!"
    echo "=========================================================================="
    echo ""
    echo "Your repository is now configured to use SSH authentication."
    echo "The automated cron job will be able to push to GitHub."
    echo ""
else
    echo -e "${RED}✗${NC} Git connection failed"
    echo ""
    echo "Possible issues:"
    echo "  1. SSH key not added to GitHub"
    echo "  2. SSH key has a passphrase (not compatible with cron)"
    echo "  3. SSH agent not running"
    echo ""
    echo "To revert to HTTPS:"
    echo "  git remote set-url origin $CURRENT_REMOTE"
    echo ""
fi
