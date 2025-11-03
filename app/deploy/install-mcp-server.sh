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

# Source shared installation helpers
source "$REPO_ROOT/scripts/install-helpers.sh"

# Configuration
MCP_USER="mcpserver"
MCP_HOME="/home/$MCP_USER"
MCP_APP_DIR="$MCP_HOME/plant-care-app"
SERVICE_NAME="plant-care-mcp.service"
SERVICE_FILE="/etc/systemd/system/$SERVICE_NAME"

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

# Check for systemd service file
if [ ! -f "$SCRIPT_DIR/$SERVICE_NAME" ]; then
    echo "ERROR: Missing systemd service file at $SCRIPT_DIR/$SERVICE_NAME"
    exit 1
fi

echo "✓ Systemd service file present"

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
add_user_to_group "$MCP_USER" "video" "for camera access"

# Add the sudo user to mcpserver group for convenient access
add_sudo_user_to_group "$MCP_USER"

# 2. Install uv package manager for mcpserver user
install_uv_for_user "$MCP_USER"
UV_BIN="$MCP_HOME/.local/bin/uv"

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

# 5b. Set up ACLs for group read access to mcpserver home
# This allows group members to read logs, configuration files, etc. via SCP
setup_acl_group_access "$MCP_USER" "$MCP_HOME"

echo "✓ ACLs configured for group access"

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
    echo ""
    echo "Note: If the service hangs or needs to be force-stopped, use:"
    echo "  sudo systemctl kill --signal=SIGKILL $SERVICE_NAME"
    echo ""
    systemctl restart "$SERVICE_NAME"
    echo "✓ Service restarted"
    SERVICE_IS_RUNNING=true
else
    SERVICE_IS_RUNNING=false
fi

# 11. Install git backup system
echo ""
echo "Installing MCP data git backup system..."

# Determine data directory path (resolve relative paths)
DATA_DIR_RAW=$(grep "^DATA_DIR=" "$MCP_HOME/.env" | cut -d'=' -f2- | tr -d '[:space:]')
if [[ "$DATA_DIR_RAW" = /* ]]; then
    # Absolute path
    MCP_DATA_DIR="$DATA_DIR_RAW"
else
    # Relative path - resolve from app directory
    MCP_DATA_DIR="$(cd "$MCP_APP_DIR" && cd "$DATA_DIR_RAW" && pwd)"
fi

echo "  Data directory: $MCP_DATA_DIR"

# Create data directory if it doesn't exist
if [ ! -d "$MCP_DATA_DIR" ]; then
    echo "  Creating data directory: $MCP_DATA_DIR"
    sudo -u "$MCP_USER" mkdir -p "$MCP_DATA_DIR"
fi

# Initialize git repository in data directory
if [ ! -d "$MCP_DATA_DIR/.git" ]; then
    echo "  Initializing git repository in $MCP_DATA_DIR"
    sudo -u "$MCP_USER" bash -c "cd '$MCP_DATA_DIR' && git init --initial-branch=main"
    sudo -u "$MCP_USER" bash -c "cd '$MCP_DATA_DIR' && git config user.name 'MCP Server Backup'"
    sudo -u "$MCP_USER" bash -c "cd '$MCP_DATA_DIR' && git config user.email 'backup@mcpserver.local'"

    # Create .gitignore
    sudo -u "$MCP_USER" bash -c "cat > '$MCP_DATA_DIR/.gitignore' << 'EOF'
# Exclude photos (too large for git)
*.jpg
*.jpeg
*.png

# Exclude temporary files
*.tmp
*.swp
*.log
EOF"

    # Make initial commit
    sudo -u "$MCP_USER" bash -c "cd '$MCP_DATA_DIR' && git add -A && git commit -m 'Initial commit' || true"
    echo "✓ Git repository initialized"
else
    echo "✓ Git repository already exists"
fi

# Add to system gitconfig so all users (including group members) can access the repo
git config --system --add safe.directory "$MCP_DATA_DIR"

# Copy backup script to mcpserver home
BACKUP_SCRIPT_SRC="$REPO_ROOT/agent/deploy/backup-mcp-data.sh"
BACKUP_SCRIPT_DEST="$MCP_HOME/backup-mcp-data.sh"

if [ ! -f "$BACKUP_SCRIPT_SRC" ]; then
    echo "⚠ Warning: Backup script not found at $BACKUP_SCRIPT_SRC"
    echo "  Skipping backup system installation"
else
    install -m 755 -o "$MCP_USER" -g "$MCP_USER" \
        "$BACKUP_SCRIPT_SRC" "$BACKUP_SCRIPT_DEST"
    echo "✓ Copied backup-mcp-data.sh"

    # Install systemd service and timer for backup
    BACKUP_SERVICE_NAME="mcpserver-data-backup.service"
    BACKUP_TIMER_NAME="mcpserver-data-backup.timer"
    BACKUP_SERVICE_FILE="/etc/systemd/system/$BACKUP_SERVICE_NAME"
    BACKUP_TIMER_FILE="/etc/systemd/system/$BACKUP_TIMER_NAME"

    BACKUP_SERVICE_TEMPLATE="$REPO_ROOT/agent/deploy/mcpserver-data-backup.service.template"
    BACKUP_TIMER_TEMPLATE="$REPO_ROOT/agent/deploy/mcpserver-data-backup.timer.template"

    if [ -f "$BACKUP_SERVICE_TEMPLATE" ] && [ -f "$BACKUP_TIMER_TEMPLATE" ]; then
        # Process service template
        sed -e "s|__MCPSERVER_USER__|$MCP_USER|g" \
            -e "s|__MCPSERVER_HOME__|$MCP_HOME|g" \
            -e "s|__MCPSERVER_DATA_DIR__|$MCP_DATA_DIR|g" \
            "$BACKUP_SERVICE_TEMPLATE" > "$BACKUP_SERVICE_FILE"
        chmod 644 "$BACKUP_SERVICE_FILE"

        # Process timer template
        sed "s|__SERVICE_NAME__|$BACKUP_SERVICE_NAME|g" \
            "$BACKUP_TIMER_TEMPLATE" > "$BACKUP_TIMER_FILE"
        chmod 644 "$BACKUP_TIMER_FILE"

        systemctl daemon-reload
        echo "✓ Backup systemd units installed"

        # Enable and start the timer
        if systemctl is-active --quiet "$BACKUP_TIMER_NAME"; then
            systemctl restart "$BACKUP_TIMER_NAME"
            echo "✓ Backup timer restarted"
        else
            systemctl enable "$BACKUP_TIMER_NAME"
            systemctl start "$BACKUP_TIMER_NAME"
            echo "✓ Backup timer enabled and started"
        fi
    else
        echo "⚠ Warning: Backup systemd templates not found"
        echo "  Service template: $BACKUP_SERVICE_TEMPLATE"
        echo "  Timer template: $BACKUP_TIMER_TEMPLATE"
    fi
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
    echo "Service Status: RUNNING"
    echo ""
    echo "Next steps:"
    echo "  1. Check service status: sudo systemctl status $SERVICE_NAME"
    echo "  2. View logs: journalctl -u $SERVICE_NAME -f"
    echo "  3. Test endpoint: curl http://localhost:8000/mcp"
    echo ""
    echo "Emergency stop (if service hangs):"
    echo "  sudo systemctl kill --signal=SIGKILL $SERVICE_NAME"
else
    # Service is not active (inactive, failed, or unknown)
    echo "Service Status: NOT RUNNING ($SERVICE_STATUS)"
    echo ""
    echo "Next steps:"
    echo "  1. Enable and start service: sudo systemctl enable --now $SERVICE_NAME"
    echo "  2. Check service status: sudo systemctl status $SERVICE_NAME"
    echo "  3. View logs: journalctl -u $SERVICE_NAME -f"
    echo "  4. Test endpoint: curl http://localhost:8000/mcp"
    echo ""
    echo "Emergency stop (if service hangs):"
    echo "  sudo systemctl kill --signal=SIGKILL $SERVICE_NAME"
fi

echo ""
echo "To update the server later:"
echo "  1. Pull latest changes: git pull origin main"
echo "  2. Re-run this script: sudo bash $0"
echo ""
