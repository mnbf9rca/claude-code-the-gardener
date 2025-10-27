#!/usr/bin/env bash

# Install the gardener site publisher on Raspberry Pi
# Run this script as the admin user with sudo
# Usage: sudo bash install-publisher.sh

set -euo pipefail

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

# Configuration
PUBLISHER_USER="gardener-publisher"
PUBLISHER_HOME="/home/${PUBLISHER_USER}"
INSTALL_DIR="${PUBLISHER_HOME}/app"
ADMIN_USER="${SUDO_USER:-$USER}"
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SITE_GEN_DIR="${REPO_DIR}/static_site_generator"

# Source shared installation helpers
source "$REPO_DIR/scripts/install-helpers.sh"

echo -e "${BLUE}🌱 Claude the Gardener - Publisher Installation${NC}"
echo "=================================================="
echo ""

# Prerequisite checks - validate before making any changes
echo "Checking prerequisites..."
echo ""

# Check we're running as root
if [[ $EUID -ne 0 ]]; then
    echo -e "${RED}Error: This script must be run with sudo${NC}"
    echo "Usage: sudo bash install-publisher.sh"
    exit 1
fi

# Ensure we were invoked via sudo (not raw root login)
if [[ -z "${SUDO_USER:-}" ]]; then
    echo -e "${RED}Error: SUDO_USER not set${NC}"
    echo "This script must be run with sudo, not as root directly"
    echo "Usage: sudo bash install-publisher.sh"
    exit 1
fi

echo -e "${GREEN}✓ Running as root${NC}"

# Check required files exist
REQUIRED_FILES=(
    "${SITE_GEN_DIR}/generate.py"
    "${SITE_GEN_DIR}/publish.sh"
    "${SITE_GEN_DIR}/orchestrate.sh"
    "${SITE_GEN_DIR}/pyproject.toml"
    "${SITE_GEN_DIR}/.env.publish.example"
    "${SITE_GEN_DIR}/deploy/gardener-site-publisher.service"
    "${SITE_GEN_DIR}/deploy/gardener-site-publisher.timer"
)

for file in "${REQUIRED_FILES[@]}"; do
    if [[ ! -f "$file" ]]; then
        echo -e "${RED}✗ Missing required file: $file${NC}"
        exit 1
    fi
done

echo -e "${GREEN}✓ All required files found${NC}"

# Check that .env.publish exists (user must create it manually)
if [[ ! -f "${SITE_GEN_DIR}/.env.publish" ]]; then
    echo -e "${RED}✗ .env.publish not found${NC}"
    echo ""
    echo "Before running this installer, you must:"
    echo "  1. Copy the template: cp ${SITE_GEN_DIR}/.env.publish.example ${SITE_GEN_DIR}/.env.publish"
    echo "  2. Edit it with your AWS credentials: nano ${SITE_GEN_DIR}/.env.publish"
    echo "  3. Set: S3_BUCKET, AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_DEFAULT_REGION"
    echo ""
    exit 1
fi

echo -e "${GREEN}✓ .env.publish exists${NC}"
echo ""

# All prerequisites passed - begin installation
echo "All prerequisites passed. Beginning installation..."
echo ""

# Create publisher user if it doesn't exist
if ! id "$PUBLISHER_USER" &>/dev/null; then
    echo -e "${BLUE}👤 Creating publisher user...${NC}"
    useradd --system --create-home --shell /bin/bash "$PUBLISHER_USER"
    echo -e "${GREEN}  ✓ User '$PUBLISHER_USER' created${NC}"
else
    echo -e "${GREEN}  ✓ User '$PUBLISHER_USER' already exists${NC}"
fi

# Add admin user to publisher group for access
add_sudo_user_to_group "$PUBLISHER_USER"

# Add publisher user to mcpserver group to read data
add_user_to_group "$PUBLISHER_USER" "mcpserver" "for data access"
echo ""

# Create installation directory
echo -e "${BLUE}📁 Creating installation directory...${NC}"
mkdir -p "$INSTALL_DIR"
echo -e "${GREEN}  ✓ Created $INSTALL_DIR${NC}"
echo ""

# Copy files
echo -e "${BLUE}📦 Copying files...${NC}"

# Copy Python files and dependencies
cp -r "${SITE_GEN_DIR}/parsers" "$INSTALL_DIR/"
cp -r "${SITE_GEN_DIR}/templates" "$INSTALL_DIR/"
cp -r "${SITE_GEN_DIR}/static" "$INSTALL_DIR/"
cp "${SITE_GEN_DIR}/generate.py" "$INSTALL_DIR/"
cp "${SITE_GEN_DIR}/pyproject.toml" "$INSTALL_DIR/"
cp "${SITE_GEN_DIR}/publish.sh" "$INSTALL_DIR/"
cp "${SITE_GEN_DIR}/orchestrate.sh" "$INSTALL_DIR/"

# Make scripts executable
chmod +x "${INSTALL_DIR}/publish.sh"
chmod +x "${INSTALL_DIR}/orchestrate.sh"

# Copy the configured .env.publish to install directory
cp "${SITE_GEN_DIR}/.env.publish" "${INSTALL_DIR}/.env.publish"

echo -e "${GREEN}  ✓ Files copied${NC}"
echo ""

# Set ownership
echo -e "${BLUE}🔐 Setting ownership...${NC}"
chown -R "${PUBLISHER_USER}:${PUBLISHER_USER}" "$INSTALL_DIR"
echo -e "${GREEN}  ✓ Ownership set to ${PUBLISHER_USER}${NC}"

# Set up ACLs for group read access to publisher home
# This allows group members to read logs, configuration files, etc. via SCP
setup_acl_group_access "$PUBLISHER_USER" "$PUBLISHER_HOME"

echo ""

# Install uv package manager
echo -e "${BLUE}🐍 Installing uv package manager...${NC}"
install_uv_for_user "$PUBLISHER_USER"
echo ""

# Install Python dependencies
echo -e "${BLUE}📦 Installing Python dependencies...${NC}"
UV_BIN="$PUBLISHER_HOME/.local/bin/uv"
sudo -u "$PUBLISHER_USER" bash -c "cd $INSTALL_DIR && $UV_BIN sync"
SYNC_EXIT_CODE=$?

if [ $SYNC_EXIT_CODE -ne 0 ]; then
    echo -e "${RED}  ✗ ERROR: uv sync failed with exit code $SYNC_EXIT_CODE${NC}" >&2
    exit 1
fi

echo -e "${GREEN}  ✓ Python dependencies installed${NC}"
echo ""

# Install AWS CLI if not already installed
echo -e "${BLUE}☁️  Checking for AWS CLI...${NC}"
if ! command -v aws &> /dev/null; then
    echo -e "${YELLOW}  ℹ️  AWS CLI not found, installing...${NC}"

    # Install AWS CLI v2 for Linux ARM (Raspberry Pi)
    if [[ $(uname -m) == "aarch64" ]]; then
        curl "https://awscli.amazonaws.com/awscli-exe-linux-aarch64.zip" -o "/tmp/awscliv2.zip"
    else
        curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "/tmp/awscliv2.zip"
    fi

    unzip -q /tmp/awscliv2.zip -d /tmp
    /tmp/aws/install
    rm -rf /tmp/awscliv2.zip /tmp/aws

    echo -e "${GREEN}  ✓ AWS CLI installed${NC}"
else
    echo -e "${GREEN}  ✓ AWS CLI already installed${NC}"
fi
echo ""

# Install systemd service and timer
echo -e "${BLUE}⚙️  Installing systemd service and timer...${NC}"

cp "${SITE_GEN_DIR}/deploy/gardener-site-publisher.service" /etc/systemd/system/
cp "${SITE_GEN_DIR}/deploy/gardener-site-publisher.timer" /etc/systemd/system/

# Reload systemd
systemctl daemon-reload

echo -e "${GREEN}  ✓ Systemd units installed${NC}"
echo ""

# Summary and next steps
echo "=================================================="
echo -e "${GREEN}✅ Installation complete!${NC}"
echo ""
echo "Next steps:"
echo ""
echo "1. Test the publisher manually (dry run):"
echo -e "   ${YELLOW}sudo -u $PUBLISHER_USER bash ${INSTALL_DIR}/orchestrate.sh --skip-sync --s3-bucket YOUR_BUCKET --dry-run${NC}"
echo ""
echo "2. Enable and start the timer:"
echo -e "   ${YELLOW}sudo systemctl enable --now gardener-site-publisher.timer${NC}"
echo ""
echo "3. Check status:"
echo -e "   ${YELLOW}systemctl status gardener-site-publisher.timer${NC}"
echo -e "   ${YELLOW}systemctl list-timers gardener-site-publisher.timer${NC}"
echo ""
echo "4. View logs:"
echo -e "   ${YELLOW}journalctl -u gardener-site-publisher -f${NC}"
echo ""
echo "Installation directory: $INSTALL_DIR"
echo ""
