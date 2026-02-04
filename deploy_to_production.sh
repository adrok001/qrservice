#!/bin/bash
# Auto-deploy script for Timeweb production server
# Usage: bash deploy_to_production.sh

set -e  # Exit on any error

echo "🚀 Starting deployment to production..."
echo ""

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Configuration
PROJECT_DIR="/var/www/qrservice"
VENV_DIR="$PROJECT_DIR/venv"
REPO_URL="https://github.com/adrok001/qrservice.git"

echo -e "${BLUE}📁 Project directory: $PROJECT_DIR${NC}"
echo ""

# Step 1: Navigate to project directory
echo -e "${BLUE}Step 1/8: Checking project directory...${NC}"
if [ ! -d "$PROJECT_DIR" ]; then
    echo -e "${RED}❌ Project directory not found. Creating...${NC}"
    mkdir -p "$PROJECT_DIR"
    cd "$PROJECT_DIR"
    git clone "$REPO_URL" .
else
    cd "$PROJECT_DIR"
    echo -e "${GREEN}✅ Project directory exists${NC}"
fi
echo ""

# Step 2: Pull latest changes from GitHub
echo -e "${BLUE}Step 2/8: Pulling latest code from GitHub...${NC}"
git fetch origin
git reset --hard origin/main
echo -e "${GREEN}✅ Code updated to latest version${NC}"
echo ""

# Step 3: Check/Create virtual environment
echo -e "${BLUE}Step 3/8: Setting up virtual environment...${NC}"
if [ ! -d "$VENV_DIR" ]; then
    echo "Creating new virtual environment..."
    python3 -m venv "$VENV_DIR"
fi
source "$VENV_DIR/bin/activate"
echo -e "${GREEN}✅ Virtual environment activated${NC}"
echo ""

# Step 4: Install/Update dependencies
echo -e "${BLUE}Step 4/8: Installing dependencies...${NC}"
pip install --upgrade pip
pip install -r requirements.txt
echo -e "${GREEN}✅ Dependencies installed${NC}"
echo ""

# Step 5: Check .env file
echo -e "${BLUE}Step 5/8: Checking .env configuration...${NC}"
if [ ! -f ".env" ]; then
    echo -e "${RED}❌ .env file not found!${NC}"
    echo "Please create .env file with production settings:"
    echo ""
    echo "Required variables:"
    echo "  SITE_URL=https://replyq.ru"
    echo "  DEBUG=False"
    echo "  SECRET_KEY=your-secret-key"
    echo "  ALLOWED_HOSTS=replyq.ru,www.replyq.ru"
    echo "  GOOGLE_OAUTH_CLIENT_ID=your-client-id"
    echo "  GOOGLE_OAUTH_CLIENT_SECRET=your-client-secret"
    echo "  YANDEX_OAUTH_CLIENT_ID=your-client-id"
    echo "  YANDEX_OAUTH_CLIENT_SECRET=your-client-secret"
    echo ""
    exit 1
else
    echo -e "${GREEN}✅ .env file exists${NC}"

    # Check critical variables
    if ! grep -q "SITE_URL=https://replyq.ru" .env; then
        echo -e "${RED}⚠️  Warning: SITE_URL should be https://replyq.ru${NC}"
    fi
    if ! grep -q "DEBUG=False" .env; then
        echo -e "${RED}⚠️  Warning: DEBUG should be False in production${NC}"
    fi
fi
echo ""

# Step 6: Run migrations
echo -e "${BLUE}Step 6/8: Running database migrations...${NC}"
python manage.py migrate --noinput
echo -e "${GREEN}✅ Migrations applied${NC}"
echo ""

# Step 7: Setup OAuth apps
echo -e "${BLUE}Step 7/8: Setting up OAuth applications...${NC}"
python manage.py setup_oauth
echo -e "${GREEN}✅ OAuth apps configured${NC}"
echo ""

# Step 8: Collect static files
echo -e "${BLUE}Step 8/8: Collecting static files...${NC}"
python manage.py collectstatic --noinput
echo -e "${GREEN}✅ Static files collected${NC}"
echo ""

# Final summary
echo ""
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}🎉 Deployment completed successfully!${NC}"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo "Next steps:"
echo "1. Restart your web server:"
echo "   sudo systemctl restart gunicorn  # or your server name"
echo ""
echo "2. Update OAuth redirect URIs in Google/Yandex consoles:"
echo "   Google: https://replyq.ru/accounts/google/login/callback/"
echo "   Yandex: https://replyq.ru/accounts/yandex/login/callback/"
echo ""
echo "3. Test the deployment:"
echo "   Visit: https://replyq.ru"
echo ""
echo "4. Test OAuth login:"
echo "   https://replyq.ru/accounts/login/"
echo ""
