#!/bin/bash
set -e

DRY_RUN=false
if [ "$1" = "--dry-run" ]; then
  DRY_RUN=true
  echo "=== DRY RUN MODE - No changes will be made ==="
  echo ""
fi

echo "=== Gardener Migration: Publisher → GitHub Sync ==="
echo ""

# Check if running as root
if [ "$EUID" -ne 0 ] && [ "$DRY_RUN" = false ]; then
  echo "ERROR: This script must be run as root (use sudo)"
  exit 1
fi

# Backup old configuration
OLD_ENV_FILE="/home/gardener-publisher/app/.env.publish"
if [ -f "$OLD_ENV_FILE" ]; then
  if [ "$DRY_RUN" = true ]; then
    echo "[DRY RUN] Would backup $OLD_ENV_FILE to ${OLD_ENV_FILE}.backup"
  else
    echo "Backing up old .env.publish..."
    cp "$OLD_ENV_FILE" "${OLD_ENV_FILE}.backup"
    echo "✓ Backup created at ${OLD_ENV_FILE}.backup"
  fi
else
  echo "No .env.publish found at $OLD_ENV_FILE (already migrated or not installed?)"
fi

# Stop old services
OLD_TIMER="gardener-site-publisher.timer"

if systemctl is-active --quiet "$OLD_TIMER"; then
  if [ "$DRY_RUN" = true ]; then
    echo "[DRY RUN] Would stop and disable $OLD_TIMER"
  else
    echo "Stopping old timer..."
    systemctl stop "$OLD_TIMER"
    systemctl disable "$OLD_TIMER"
    echo "✓ Old timer stopped and disabled"
  fi
else
  echo "Old timer not active (already migrated?)"
fi

# Run installation script
if [ "$DRY_RUN" = true ]; then
  echo ""
  echo "[DRY RUN] Would run install-data-sync.sh to set up new system"
  echo ""
  echo "=== Dry Run Complete ==="
  echo ""
  echo "To execute migration, run:"
  echo "  sudo bash $(basename "$0")"
  exit 0
fi

echo ""
echo "Running installation script..."
bash "$(dirname "$0")/install-data-sync.sh"

echo ""
echo "=== Migration Complete ==="
echo ""
echo "New system is now active. Old system is stopped but not deleted."
echo ""
echo "Rollback instructions (if needed):"
echo "  sudo systemctl disable --now gardener-data-sync.timer"
echo "  sudo systemctl enable --now $OLD_TIMER"
echo ""
echo "After 1 week of stability, clean up old system:"
echo "  sudo rm /etc/systemd/system/gardener-site-publisher.{service,timer}"
echo "  sudo rm -rf /home/gardener-publisher/app/output/.git"
echo "  sudo systemctl daemon-reload"
