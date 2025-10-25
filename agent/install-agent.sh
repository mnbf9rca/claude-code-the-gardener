#!/bin/bash
set -euo pipefail

# Idempotent installation script for Claude Code gardener agent
# Run as admin user with sudo: sudo bash agent/install-agent.sh

echo "=== Claude Code Gardener Agent Installation ==="

# Ensure running as root
if [ "$EUID" -ne 0 ]; then
    echo "ERROR: This script must be run with sudo"
    exit 1
fi

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
DEPLOY_DIR="$SCRIPT_DIR/deploy"

# Source shared installation helpers
source "$REPO_ROOT/scripts/install-helpers.sh"

# Configuration
GARDENER_USER="gardener"
GARDENER_HOME="/home/gardener"
GARDENER_WORKSPACE="$GARDENER_HOME/workspace"
GARDENER_CLAUDE_DIR="$GARDENER_WORKSPACE/.claude"
SERVICE_NAME="gardener-agent.service"
SERVICE_FILE="/etc/systemd/system/$SERVICE_NAME"

echo "Repository root: $REPO_ROOT"
echo "Script directory: $SCRIPT_DIR"
echo "Deploy directory: $DEPLOY_DIR"

# Prerequisite checks - validate before making any changes
echo ""
echo "Checking prerequisites..."

# Check for required configuration files
MISSING_FILES=()
if [ ! -f "$DEPLOY_DIR/.env.agent" ]; then
    MISSING_FILES+=(".env.agent")
fi
if [ ! -f "$DEPLOY_DIR/prompt.txt" ]; then
    MISSING_FILES+=("prompt.txt")
fi
if [ ! -f "$DEPLOY_DIR/.mcp.json" ]; then
    MISSING_FILES+=(".mcp.json")
fi
if [ ! -f "$DEPLOY_DIR/settings.json" ]; then
    MISSING_FILES+=("settings.json")
fi
if [ ! -f "$DEPLOY_DIR/run-agent.sh" ]; then
    MISSING_FILES+=("run-agent.sh")
fi
if [ ! -f "$DEPLOY_DIR/gardener-agent.service.template" ]; then
    MISSING_FILES+=("gardener-agent.service.template")
fi
if [ ! -f "$DEPLOY_DIR/gardener-agent.timer.template" ]; then
    MISSING_FILES+=("gardener-agent.timer.template")
fi

if [ ${#MISSING_FILES[@]} -gt 0 ]; then
    echo "ERROR: Missing required files in $DEPLOY_DIR:"
    for file in "${MISSING_FILES[@]}"; do
        echo "  - $file"
    done
    echo ""
    echo "Please ensure all required files exist before running installation."
    if [[ " ${MISSING_FILES[@]} " =~ " .env.agent " ]]; then
        echo "  Create .env.agent from .env.agent.example template"
        echo "  Example: cp $SCRIPT_DIR/.env.agent.example $DEPLOY_DIR/.env.agent"
    fi
    exit 1
fi

echo "✓ All required files present"
echo ""

# 1. Create gardener user if it doesn't exist
if id "$GARDENER_USER" &>/dev/null; then
    echo "✓ User $GARDENER_USER already exists"
else
    if [ -d "$GARDENER_HOME" ]; then
        echo "⚠ Warning: $GARDENER_HOME already exists but user does not"
        echo "  The directory may have incorrect permissions"
        echo "  Consider removing it: sudo rm -rf $GARDENER_HOME"
        echo ""
        echo "*****************************************************************************************"
        echo "*                                                                                       *"
        echo "*   ⚠ Warning: deleting these folders will remove any existing configuration and data!  *"
        echo "*   For example agent logs or ~/.claude/projects/ may contain detailed transcripts.     *"
        echo "*                                                                                       *"
        echo "*****************************************************************************************"
        exit 1
    fi
    echo "Creating user $GARDENER_USER..."
    useradd --system --create-home --shell /usr/sbin/nologin "$GARDENER_USER"
    echo "✓ User $GARDENER_USER created"
fi

# Add the sudo user to gardener group for convenient access
add_sudo_user_to_group "$GARDENER_USER"

# 2. Create necessary directories
echo "Creating directories..."
mkdir -p "$GARDENER_HOME/logs"
mkdir -p "$GARDENER_WORKSPACE"
mkdir -p "$GARDENER_CLAUDE_DIR"
chown "$GARDENER_USER:$GARDENER_USER" "$GARDENER_HOME/logs"
chown -R "$GARDENER_USER:$GARDENER_USER" "$GARDENER_WORKSPACE"

# Enable group read+execute access to entire gardener home using ACLs
# This allows group members to read files (e.g., Claude Code project transcripts) via SCP
# Default ACLs ensure future files/directories also get group permissions
setup_acl_group_access "$GARDENER_USER" "$GARDENER_HOME"

echo "✓ Directories created and ACLs configured"

# 3. Install Claude Code CLI as gardener user
CLAUDE_BIN="$GARDENER_HOME/.local/bin/claude"
if [ -x "$CLAUDE_BIN" ]; then
    CLAUDE_VERSION=$(sudo -u "$GARDENER_USER" "$CLAUDE_BIN" --version 2>/dev/null || echo "unknown")
    echo "✓ Claude Code CLI already installed (version: $CLAUDE_VERSION)"
else
    echo "Installing Claude Code CLI as $GARDENER_USER..."
    echo ""

    # Run installation with visible output from gardener's home directory
    sudo -u "$GARDENER_USER" bash -c "cd $GARDENER_HOME && curl -fsSL https://claude.ai/install.sh | bash"
    INSTALL_EXIT_CODE=$?

    echo ""

    # Validate installation
    if [ $INSTALL_EXIT_CODE -ne 0 ]; then
        echo "✗ ERROR: Claude Code CLI installation script failed with exit code $INSTALL_EXIT_CODE" >&2
        exit 1
    fi

    if [ -x "$CLAUDE_BIN" ]; then
        CLAUDE_VERSION=$(sudo -u "$GARDENER_USER" "$CLAUDE_BIN" --version 2>/dev/null || echo "unknown")
        echo "✓ Claude Code CLI installed successfully (version: $CLAUDE_VERSION)"
    else
        echo "✗ ERROR: Claude Code CLI installation failed - binary not found at $CLAUDE_BIN" >&2
        exit 1
    fi
fi

# 4. Copy configuration files to gardener home (read-only for gardener)
echo "Copying configuration files..."

# Copy run-agent.sh (executable, but read-only for gardener)
install -m 755 -o root -g root \
    "$DEPLOY_DIR/run-agent.sh" "$GARDENER_HOME/run-agent.sh"
echo "✓ Copied run-agent.sh"

# Copy prompt.txt (read-only for gardener)
install -m 644 -o root -g root \
    "$DEPLOY_DIR/prompt.txt" "$GARDENER_HOME/prompt.txt"
echo "✓ Copied prompt.txt"

# Copy .mcp.json (read-only for gardener)
install -m 644 -o root -g root \
    "$DEPLOY_DIR/.mcp.json" "$GARDENER_HOME/.mcp.json"
echo "✓ Copied .mcp.json"

# Copy settings.json to .claude directory (read-only for gardener)
install -m 644 -o root -g root \
    "$DEPLOY_DIR/settings.json" "$GARDENER_CLAUDE_DIR/settings.json"
echo "✓ Copied settings.json"

# Copy .env.agent (readable by gardener via group permissions)
install -m 640 -o root -g "$GARDENER_USER" \
    "$DEPLOY_DIR/.env.agent" "$GARDENER_HOME/.env.agent"
echo "✓ Copied .env.agent"

# 5. Install systemd service and timer from templates
echo "Installing systemd service and timer..."

# Define timer variables
TIMER_NAME="${SERVICE_NAME%.service}.timer"
TIMER_FILE="/etc/systemd/system/$TIMER_NAME"

# Process service template with variable substitution
sed -e "s|__GARDENER_USER__|$GARDENER_USER|g" \
    -e "s|__GARDENER_HOME__|$GARDENER_HOME|g" \
    "$DEPLOY_DIR/gardener-agent.service.template" > "$SERVICE_FILE"

chmod 644 "$SERVICE_FILE"
echo "✓ Service file created from template"

# Process timer template with variable substitution
sed "s|__SERVICE_NAME__|$SERVICE_NAME|g" \
    "$DEPLOY_DIR/gardener-agent.timer.template" > "$TIMER_FILE"

chmod 644 "$TIMER_FILE"
echo "✓ Timer file created from template"

systemctl daemon-reload
echo "✓ Systemd service and timer installed"

# 7. Summary
echo ""
echo "=== Installation Complete ==="
echo ""
echo "Next steps:"
echo "  1. Test manually: sudo -u $GARDENER_USER $GARDENER_HOME/run-agent.sh"
echo "     (Script will run once and exit - this is expected!)"
echo "  2. Enable timer: sudo systemctl enable --now $TIMER_NAME"
echo "  3. Monitor logs: journalctl -u $SERVICE_NAME -f"
echo "  4. Check timer status: systemctl status $TIMER_NAME"
echo "  5. List timer schedule: systemctl list-timers $TIMER_NAME"
echo "  6. Check health: https://healthchecks.io/checks/"
echo ""
echo "Note: The agent now runs via systemd timer, not as a continuous service."
echo "Timer triggers the service 15 minutes after each run completes."
echo ""
echo "To update configuration later:"
echo "  - Edit files in $DEPLOY_DIR/"
echo "  - Re-run this script: sudo bash $0"
echo "  - Restart timer: sudo systemctl restart $TIMER_NAME"
