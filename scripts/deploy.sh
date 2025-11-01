#!/bin/bash
# Automated deployment script for AI News Crawler
# This script sets up the application from scratch on a fresh system

set -e  # Exit on error
set -u  # Exit on undefined variable

# Configuration
APP_NAME="ai-news-crawler"
APP_DIR="/opt/$APP_NAME"
USER="crawler"
LOG_DIR="/var/log/$APP_NAME"

echo "=========================================="
echo "AI News Crawler Deployment Script"
echo "=========================================="
echo ""

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo "ERROR: This script must be run as root (use sudo)"
    exit 1
fi

# Step 1: Create user if not exists
echo "Step 1: Creating system user..."
if ! id "$USER" &>/dev/null; then
    useradd -r -s /bin/bash -d "$APP_DIR" "$USER"
    echo "  ✓ Created user: $USER"
else
    echo "  ✓ User already exists: $USER"
fi

# Step 2: Create directories
echo "Step 2: Creating application directories..."
mkdir -p "$APP_DIR"
mkdir -p "$LOG_DIR"
mkdir -p "$APP_DIR/output"
chown -R "$USER:$USER" "$APP_DIR"
chown -R "$USER:$USER" "$LOG_DIR"
echo "  ✓ Created directories"

# Step 3: Copy application files
echo "Step 3: Copying application files..."
if [ -d "$(dirname "$0")/.." ]; then
    cp -r "$(dirname "$0")/../"* "$APP_DIR/" 2>/dev/null || true
    chown -R "$USER:$USER" "$APP_DIR"
    echo "  ✓ Application files copied"
else
    echo "  ⚠ Warning: Application files not found. Please copy manually."
fi

# Step 4: Install system dependencies
echo "Step 4: Installing system dependencies..."
apt-get update -qq
apt-get install -y -qq python3 python3-pip python3-venv postgresql redis-server
echo "  ✓ System dependencies installed"

# Step 5: Create virtual environment
echo "Step 5: Creating Python virtual environment..."
if [ ! -d "$APP_DIR/venv" ]; then
    sudo -u "$USER" python3 -m venv "$APP_DIR/venv"
    echo "  ✓ Virtual environment created"
else
    echo "  ✓ Virtual environment already exists"
fi

# Step 6: Install Python dependencies
echo "Step 6: Installing Python dependencies..."
sudo -u "$USER" "$APP_DIR/venv/bin/pip" install --upgrade pip -q
sudo -u "$USER" "$APP_DIR/venv/bin/pip" install -r "$APP_DIR/requirements.txt" -q
echo "  ✓ Python dependencies installed"

# Step 7: Database setup
echo "Step 7: Setting up PostgreSQL database..."
if sudo -u postgres psql -lqt | cut -d \| -f 1 | grep -qw ai_news_crawler; then
    echo "  ✓ Database already exists"
else
    sudo -u postgres psql -c "CREATE DATABASE ai_news_crawler;" 2>/dev/null || true
    sudo -u postgres psql -c "CREATE USER crawler WITH ENCRYPTED PASSWORD 'change_me_in_production';" 2>/dev/null || true
    sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE ai_news_crawler TO crawler;" 2>/dev/null || true
    echo "  ✓ Database created"
fi

# Step 8: Copy environment file
echo "Step 8: Configuring environment..."
if [ ! -f "$APP_DIR/.env" ]; then
    cp "$APP_DIR/.env.example" "$APP_DIR/.env"
    chown "$USER:$USER" "$APP_DIR/.env"
    chmod 600 "$APP_DIR/.env"
    echo "  ✓ Environment file created from template"
    echo "  ⚠ WARNING: Please edit $APP_DIR/.env with your API keys and credentials!"
else
    echo "  ✓ Environment file already exists"
fi

# Step 9: Run database migrations
echo "Step 9: Running database migrations..."
cd "$APP_DIR"
if [ -f "$APP_DIR/.env" ]; then
    sudo -u "$USER" bash -c "cd $APP_DIR && source venv/bin/activate && alembic upgrade head" 2>/dev/null || \
        echo "  ⚠ Migration skipped (run manually after configuring .env)"
else
    echo "  ⚠ Skipping migrations (configure .env first)"
fi

# Step 10: Install systemd service
echo "Step 10: Installing systemd service..."
if [ -f "$APP_DIR/deployment/ai-news-crawler.service" ]; then
    cp "$APP_DIR/deployment/ai-news-crawler.service" /etc/systemd/system/
    cp "$APP_DIR/deployment/ai-news-crawler.timer" /etc/systemd/system/
    systemctl daemon-reload
    systemctl enable ai-news-crawler.timer
    echo "  ✓ Systemd service installed and enabled"
else
    echo "  ⚠ Systemd files not found"
fi

# Step 11: Set permissions
echo "Step 11: Setting file permissions..."
chown -R "$USER:$USER" "$APP_DIR"
chmod 700 "$APP_DIR/.env" 2>/dev/null || true
echo "  ✓ Permissions set"

echo ""
echo "=========================================="
echo "Deployment completed successfully!"
echo "=========================================="
echo ""
echo "Next steps:"
echo "1. Edit $APP_DIR/.env with your API keys and credentials"
echo "2. Test the crawler: sudo -u $USER $APP_DIR/venv/bin/python -m crawler"
echo "3. Start the timer: sudo systemctl start ai-news-crawler.timer"
echo "4. Check status: sudo systemctl status ai-news-crawler.timer"
echo "5. View logs: sudo journalctl -u ai-news-crawler -f"
echo ""
echo "Manual test run:"
echo "  sudo systemctl start ai-news-crawler.service"
echo ""
