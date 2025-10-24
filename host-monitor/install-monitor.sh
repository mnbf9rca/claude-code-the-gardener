#!/bin/bash
set -euo pipefail

# Idempotent installation script for host healthcheck monitor
# Run with sudo: sudo bash host-monitor/install-monitor.sh

echo "=== Host Healthcheck Monitor Installation ==="

# Ensure running as root
if [ "$EUID" -ne 0 ]; then
    echo "ERROR: This script must be run with sudo"
    exit 1
fi

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Configuration
SERVICE_NAME="host-healthcheck"
TIMER_NAME="${SERVICE_NAME}.timer"
SERVICE_FILE="${SERVICE_NAME}.service"
SYSTEMD_DIR="/etc/systemd/system"

echo "Script directory: $SCRIPT_DIR"
echo ""

# Prerequisite checks
echo "Checking prerequisites..."

# Check for curl
if ! command -v curl &> /dev/null; then
    echo "ERROR: curl is not installed"
    echo "Install with: sudo apt-get install curl"
    exit 1
fi
echo "✓ curl is installed"

# Check for required files
MISSING_FILES=()
if [ ! -f "$SCRIPT_DIR/$SERVICE_FILE" ]; then
    MISSING_FILES+=("$SERVICE_FILE")
fi
if [ ! -f "$SCRIPT_DIR/$TIMER_NAME" ]; then
    MISSING_FILES+=("$TIMER_NAME")
fi

if [ ${#MISSING_FILES[@]} -gt 0 ]; then
    echo "ERROR: Missing required files in $SCRIPT_DIR:"
    for file in "${MISSING_FILES[@]}"; do
        echo "  - $file"
    done
    exit 1
fi
echo "✓ All required files present"
echo ""

# Install systemd service and timer
echo "Installing systemd service and timer..."

# Copy service file
install -m 644 "$SCRIPT_DIR/$SERVICE_FILE" "$SYSTEMD_DIR/$SERVICE_FILE"
echo "✓ Installed $SERVICE_FILE"

# Copy timer file
install -m 644 "$SCRIPT_DIR/$TIMER_NAME" "$SYSTEMD_DIR/$TIMER_NAME"
echo "✓ Installed $TIMER_NAME"

# Reload systemd
systemctl daemon-reload
echo "✓ Systemd daemon reloaded"

# Enable and start timer
systemctl enable "$TIMER_NAME"
echo "✓ Timer enabled (will start on boot)"

systemctl start "$TIMER_NAME"
echo "✓ Timer started"

echo ""
echo "=== Installation Complete ==="
echo ""
echo "Monitor healthcheck pings at:"
echo "  https://hc-ping.com/6ebf0433-7488-4ab8-90b6-e221b9b4d431"
echo ""
echo "Useful commands:"
echo "  - Check timer status:  systemctl status $TIMER_NAME"
echo "  - List active timers:  systemctl list-timers $TIMER_NAME"
echo "  - View service logs:   journalctl -u $SERVICE_FILE -f"
echo "  - Restart timer:       sudo systemctl restart $TIMER_NAME"
echo "  - Disable timer:       sudo systemctl disable --now $TIMER_NAME"
echo ""
echo "To uninstall:"
echo "  sudo systemctl disable --now $TIMER_NAME"
echo "  sudo rm $SYSTEMD_DIR/$SERVICE_FILE $SYSTEMD_DIR/$TIMER_NAME"
echo "  sudo systemctl daemon-reload"
echo ""
