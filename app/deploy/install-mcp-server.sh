#!/bin/bash
set -euo pipefail

# Idempotent installation script for Plant Care MCP Server
# Run as admin user with sudo: sudo bash app/deploy/install-mcp-server.sh

echo "=== Plant Care MCP Server Installation ==="

# Ensure running as root
if [ "$EUID" -ne 0 ]; then
    echo "ERROR: This script must be run with sudo"
    exit 1
fi

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
REPO_ROOT="$(cd "$APP_DIR/.." && pwd)"

# Configuration
MCP_USER="mcpserver"
MCP_HOME="/home/$MCP_USER"
MCP_APP_DIR="$MCP_HOME/plant-care-app"
SERVICE_NAME="plant-care-mcp.service"
SERVICE_FILE="/etc/systemd/system/$SERVICE_NAME"
CAMERA_SERVICE_NAME="camera-focus.service"
CAMERA_SERVICE_FILE="/etc/systemd/system/$CAMERA_SERVICE_NAME"

echo "Repository root: $REPO_ROOT"
echo "App directory: $APP_DIR"
echo "Script directory: $SCRIPT_DIR"

# Prerequisite checks - validate before making any changes
echo ""
echo "Checking prerequisites..."

# Check for rsync (required for file deployment)
if ! command -v rsync &> /dev/null; then
    echo "ERROR: rsync is not installed"
    echo "  Install it with: sudo apt-get install rsync"
    exit 1
fi

echo "✓ rsync available"

# Check for .env file
if [ ! -f "$APP_DIR/.env" ]; then
    echo "ERROR: Missing .env file at $APP_DIR/.env"
    echo ""
    echo "Please create .env from the template:"
    echo "  cp $APP_DIR/.env.example $APP_DIR/.env"
    echo "  # Edit $APP_DIR/.env with appropriate configuration"
    echo ""
    echo "REQUIRED settings for mcpserver deployment:"
    echo "  DATA_DIR=../data                  # JSONL history storage (outside app dir)"
    echo "  CAMERA_SAVE_PATH=../photos        # Photo storage (outside app dir)"
    echo "  MCP_HOST=0.0.0.0"
    echo "  MCP_PORT=8000"
    exit 1
fi

echo "✓ .env file present"

# Validate required environment variables in .env
echo "Validating required environment variables..."
ENV_ERRORS=0

# Check DATA_DIR
DATA_DIR_VALUE=$(grep "^DATA_DIR=" "$APP_DIR/.env" | cut -d'=' -f2- | tr -d '[:space:]')
if ! grep -q "^DATA_DIR=" "$APP_DIR/.env"; then
    echo "✗ ERROR: DATA_DIR not set in .env"
    ENV_ERRORS=$((ENV_ERRORS + 1))
elif [ -z "$DATA_DIR_VALUE" ]; then
    echo "✗ ERROR: DATA_DIR is empty in .env"
    ENV_ERRORS=$((ENV_ERRORS + 1))
fi

# Check CAMERA_SAVE_PATH
CAMERA_SAVE_PATH_VALUE=$(grep "^CAMERA_SAVE_PATH=" "$APP_DIR/.env" | cut -d'=' -f2- | tr -d '[:space:]')
if ! grep -q "^CAMERA_SAVE_PATH=" "$APP_DIR/.env"; then
    echo "✗ ERROR: CAMERA_SAVE_PATH not set in .env"
    ENV_ERRORS=$((ENV_ERRORS + 1))
elif [ -z "$CAMERA_SAVE_PATH_VALUE" ]; then
    echo "✗ ERROR: CAMERA_SAVE_PATH is empty in .env"
    ENV_ERRORS=$((ENV_ERRORS + 1))
fi

if [ $ENV_ERRORS -gt 0 ]; then
    echo ""
    echo "ERROR: Required environment variables missing from .env"
    echo ""
    echo "Data directories MUST be configured outside the application directory."
    echo "The install script deletes /home/mcpserver/plant-care-app on updates."
    echo ""
    echo "Add to $APP_DIR/.env:"
    echo "  DATA_DIR=../data              # Recommended: relative path"
    echo "  CAMERA_SAVE_PATH=../photos    # Recommended: relative path"
    echo ""
    echo "Or use absolute paths:"
    echo "  DATA_DIR=/var/lib/plant-care/data"
    echo "  CAMERA_SAVE_PATH=/var/lib/plant-care/photos"
    exit 1
fi

echo "✓ Required environment variables present (DATA_DIR, CAMERA_SAVE_PATH)"

# Check for systemd service files
if [ ! -f "$SCRIPT_DIR/$SERVICE_NAME" ]; then
    echo "ERROR: Missing systemd service file at $SCRIPT_DIR/$SERVICE_NAME"
    exit 1
fi

if [ ! -f "$SCRIPT_DIR/$CAMERA_SERVICE_NAME" ]; then
    echo "ERROR: Missing camera systemd service file at $SCRIPT_DIR/$CAMERA_SERVICE_NAME"
    exit 1
fi

echo "✓ Systemd service files present"

# Check for pyproject.toml
if [ ! -f "$APP_DIR/pyproject.toml" ]; then
    echo "ERROR: Missing pyproject.toml at $APP_DIR/pyproject.toml"
    exit 1
fi

echo "✓ pyproject.toml present"

# Check for run_http.py
if [ ! -f "$APP_DIR/run_http.py" ]; then
    echo "ERROR: Missing run_http.py at $APP_DIR/run_http.py"
    exit 1
fi

echo "✓ run_http.py present"
echo ""

# 1. Create and configure mcpserver user
if id "$MCP_USER" &>/dev/null; then
    echo "✓ User $MCP_USER already exists"
else
    if [ -d "$MCP_HOME" ]; then
        echo "⚠ Warning: $MCP_HOME already exists but user does not"
        echo "  The directory may have incorrect permissions"
        echo "  Consider removing it: sudo rm -rf $MCP_HOME"
        echo ""
        echo "*****************************************************************************************"
        echo "*                                                                                       *"
        echo "*   ⚠ Warning: deleting this folder will remove any existing configuration and data!   *"
        echo "*   For example logs, photos, and state files may contain important information.       *"
        echo "*                                                                                       *"
        echo "*****************************************************************************************"
        exit 1
    fi
    echo "Creating user $MCP_USER..."
    useradd --system --create-home --shell /usr/sbin/nologin "$MCP_USER"
    echo "✓ User $MCP_USER created"
fi

# Add mcpserver to video group for camera access
if ! groups "$MCP_USER" | grep -q '\bvideo\b'; then
    echo "Adding $MCP_USER to video group for camera access..."
    if ! usermod -a -G video "$MCP_USER"; then
        echo "✗ ERROR: Failed to add $MCP_USER to video group" >&2
        echo "  Camera access will not work without video group membership" >&2
        exit 1
    fi
    echo "✓ User $MCP_USER added to video group"
else
    echo "✓ User $MCP_USER already in video group"
fi

# 2. Install uv package manager for mcpserver user
UV_BIN="$MCP_HOME/.local/bin/uv"
if [ -x "$UV_BIN" ]; then
    UV_VERSION=$(sudo -u "$MCP_USER" "$UV_BIN" --version 2>/dev/null || echo "unknown")
    echo "✓ uv already installed (version: $UV_VERSION)"
else
    echo "Installing uv package manager as $MCP_USER..."
    echo ""

    # Run uv installation with visible output
    sudo -u "$MCP_USER" bash -c "cd $MCP_HOME && curl -LsSf https://astral.sh/uv/install.sh | sh"
    INSTALL_EXIT_CODE=$?

    echo ""

    # Validate installation
    if [ $INSTALL_EXIT_CODE -ne 0 ]; then
        echo "✗ ERROR: uv installation script failed with exit code $INSTALL_EXIT_CODE" >&2
        exit 1
    fi

    if [ -x "$UV_BIN" ]; then
        UV_VERSION=$(sudo -u "$MCP_USER" "$UV_BIN" --version 2>/dev/null || echo "unknown")
        echo "✓ uv installed successfully (version: $UV_VERSION)"
    else
        echo "✗ ERROR: uv installation failed - binary not found at $UV_BIN" >&2
        exit 1
    fi
fi

# 3. Copy app directory to mcpserver home
echo "Copying application files..."

# Safety check before removing old installation
if [ -d "$MCP_APP_DIR" ]; then
    # Verify it's under /home/mcpserver to prevent accidents
    if [[ "$MCP_APP_DIR" != /home/mcpserver/* ]]; then
        echo "✗ ERROR: Refusing to remove directory outside /home/mcpserver: $MCP_APP_DIR" >&2
        exit 1
    fi
    echo "  Removing old installation at $MCP_APP_DIR"
    rm -rf "$MCP_APP_DIR"
fi

# Use rsync to copy only necessary files, excluding build artifacts and test data
# This ensures a clean deployment without .venv, __pycache__, test artifacts, etc.
# Note: data/ and photos/ should be configured outside app dir via DATA_DIR and CAMERA_SAVE_PATH
# but we exclude them here for safety in case they exist in development environment
mkdir -p "$MCP_APP_DIR"
rsync -a \
    --exclude='.venv/' \
    --exclude='__pycache__/' \
    --exclude='.pytest_cache/' \
    --exclude='.ruff_cache/' \
    --exclude='.mypy_cache/' \
    --exclude='data/' \
    --exclude='photos/' \
    --exclude='test_photos/' \
    --exclude='.env' \
    --exclude='*.pyc' \
    --exclude='*.pyo' \
    --exclude='.DS_Store' \
    "$APP_DIR/" "$MCP_APP_DIR/"
echo "✓ Copied application files to $MCP_APP_DIR"

# 4. Create deployment info file
echo "Creating deployment metadata..."
cat > "$MCP_APP_DIR/.deployment-info" << EOF
DEPLOYED_AT=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
GIT_COMMIT=$(cd "$REPO_ROOT" && git rev-parse HEAD 2>/dev/null || echo "unknown")
GIT_BRANCH=$(cd "$REPO_ROOT" && git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "unknown")
DEPLOYED_BY=$(logname 2>/dev/null || echo "$SUDO_USER")
EOF
echo "✓ Deployment info written to .deployment-info"

# 5. Set ownership of app directory
chown -R "$MCP_USER:$MCP_USER" "$MCP_APP_DIR"
echo "✓ Set ownership of $MCP_APP_DIR"

# 6. Install Python dependencies
echo "Installing Python dependencies..."
echo ""

# Run uv sync from the app directory
sudo -u "$MCP_USER" bash -c "cd $MCP_APP_DIR && $UV_BIN sync"
SYNC_EXIT_CODE=$?

echo ""

if [ $SYNC_EXIT_CODE -ne 0 ]; then
    echo "✗ ERROR: uv sync failed with exit code $SYNC_EXIT_CODE" >&2
    exit 1
fi

echo "✓ Python dependencies installed"

# 7. Copy .env configuration
echo "Copying environment configuration..."
install -m 640 -o root -g "$MCP_USER" \
    "$APP_DIR/.env" "$MCP_HOME/.env"
echo "✓ Copied .env to $MCP_HOME/.env"

# 8. Check if service is currently running (before any changes)
SERVICE_WAS_ACTIVE=false
if systemctl is-active --quiet "$SERVICE_NAME" 2>/dev/null; then
    SERVICE_WAS_ACTIVE=true
fi

# 9. Install systemd service
echo "Installing systemd service..."
SERVICE_FILE_UPDATED=false
if [ -f "$SERVICE_FILE" ]; then
    if ! cmp -s "$SCRIPT_DIR/$SERVICE_NAME" "$SERVICE_FILE"; then
        echo "  Service file differs - stopping service before updating..."
        systemctl stop "$SERVICE_NAME" 2>/dev/null || true
        cp "$SCRIPT_DIR/$SERVICE_NAME" "$SERVICE_FILE"
        chmod 644 "$SERVICE_FILE"
        systemctl daemon-reload
        SERVICE_FILE_UPDATED=true
        echo "✓ Systemd service updated"
    else
        echo "  Service file unchanged - skipping update"
    fi
else
    cp "$SCRIPT_DIR/$SERVICE_NAME" "$SERVICE_FILE"
    chmod 644 "$SERVICE_FILE"
    systemctl daemon-reload
    echo "✓ Systemd service installed"
fi

# 10. Restart service if it was running or if we updated files
if [ "$SERVICE_WAS_ACTIVE" = true ] || [ "$SERVICE_FILE_UPDATED" = true ]; then
    echo "  Restarting service with updated configuration..."
    systemctl restart "$SERVICE_NAME"
    echo "✓ Service restarted"
    SERVICE_IS_RUNNING=true
else
    SERVICE_IS_RUNNING=false
fi

# 11. Install camera focus service
echo "Installing camera focus systemd service..."
CAMERA_SERVICE_UPDATED=false
if [ -f "$CAMERA_SERVICE_FILE" ]; then
    if ! cmp -s "$SCRIPT_DIR/$CAMERA_SERVICE_NAME" "$CAMERA_SERVICE_FILE"; then
        echo "  Camera service file differs - updating..."
        cp "$SCRIPT_DIR/$CAMERA_SERVICE_NAME" "$CAMERA_SERVICE_FILE"
        chmod 644 "$CAMERA_SERVICE_FILE"
        systemctl daemon-reload
        CAMERA_SERVICE_UPDATED=true
        echo "✓ Camera service updated"
    else
        echo "  Camera service file unchanged - skipping update"
    fi
else
    cp "$SCRIPT_DIR/$CAMERA_SERVICE_NAME" "$CAMERA_SERVICE_FILE"
    chmod 644 "$CAMERA_SERVICE_FILE"
    systemctl daemon-reload
    echo "✓ Camera service installed"
fi

# Enable and start camera service (always, it's lightweight and idempotent)
if ! systemctl is-enabled --quiet "$CAMERA_SERVICE_NAME" 2>/dev/null; then
    systemctl enable "$CAMERA_SERVICE_NAME"
    echo "✓ Camera service enabled"
fi

# Start camera service if not already running or if updated
if ! systemctl is-active --quiet "$CAMERA_SERVICE_NAME" 2>/dev/null || [ "$CAMERA_SERVICE_UPDATED" = true ]; then
    systemctl start "$CAMERA_SERVICE_NAME"
    echo "✓ Camera service started"
fi

# 12. Summary
echo ""
echo "=== Installation Complete ==="
echo ""

# Display deployment info
echo "Deployment Information:"
cat "$MCP_APP_DIR/.deployment-info" | sed 's/^/  /'
echo ""

echo "App Directory: $MCP_APP_DIR"
echo ""

# Check actual service status (more reliable than tracking state during script)
SERVICE_STATUS=$(systemctl is-active "$SERVICE_NAME" 2>/dev/null || echo "inactive")
# Trim leading and trailing whitespace only
SERVICE_STATUS=$(echo "$SERVICE_STATUS" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')

if [ "$SERVICE_STATUS" = "active" ]; then
    echo "MCP Service Status: RUNNING"
else
    # Service is not active (inactive, failed, or unknown)
    echo "MCP Service Status: NOT RUNNING ($SERVICE_STATUS)"
fi

# Check camera service status
CAMERA_SERVICE_STATUS=$(systemctl is-active "$CAMERA_SERVICE_NAME" 2>/dev/null || echo "inactive")
CAMERA_SERVICE_STATUS=$(echo "$CAMERA_SERVICE_STATUS" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')

if [ "$CAMERA_SERVICE_STATUS" = "active" ]; then
    echo "Camera Focus Service: CONFIGURED"
else
    echo "Camera Focus Service: NOT RUNNING ($CAMERA_SERVICE_STATUS)"
fi

echo ""

if [ "$SERVICE_STATUS" = "active" ]; then
    echo "Next steps:"
    echo "  1. Check service status: sudo systemctl status $SERVICE_NAME"
    echo "  2. View logs: journalctl -u $SERVICE_NAME -f"
    echo "  3. Test endpoint: curl http://localhost:8000/mcp"
    echo "  4. Camera focus: See docs/camera_setup.md for calibration"
else
    echo "Next steps:"
    echo "  1. Enable and start service: sudo systemctl enable --now $SERVICE_NAME"
    echo "  2. Check service status: sudo systemctl status $SERVICE_NAME"
    echo "  3. View logs: journalctl -u $SERVICE_NAME -f"
    echo "  4. Test endpoint: curl http://localhost:8000/mcp"
    echo "  5. Camera focus: See docs/camera_setup.md for calibration"
fi

echo ""
echo "To update the server later:"
echo "  1. Pull latest changes: git pull origin main"
echo "  2. Re-run this script: sudo bash $0"
echo ""
