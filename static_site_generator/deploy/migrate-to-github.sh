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
if [ -f "/home/gardener/.env.publish" ]; then
  if [ "$DRY_RUN" = true ]; then
    echo "[DRY RUN] Would backup .env.publish to .env.publish.backup"
  else
    echo "Backing up old .env.publish..."
    cp /home/gardener/.env.publish /home/gardener/.env.publish.backup
    echo "✓ Backup created"
  fi
else
  echo "No .env.publish found (already migrated?)"
fi

# Stop old services
OLD_TIMER="gardener-site-publisher.timer"
OLD_SERVICE="gardener-site-publisher.service"

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

# Remove old output/.git (change tracking)
OLD_OUTPUT_GIT="/home/gardener/claude-code-the-gardener/static_site_generator/output/.git"
if [ -d "$OLD_OUTPUT_GIT" ]; then
  if [ "$DRY_RUN" = true ]; then
    echo "[DRY RUN] Would remove $OLD_OUTPUT_GIT"
  else
    echo "Removing old output/.git directory..."
    rm -rf "$OLD_OUTPUT_GIT"
    echo "✓ Old git tracking removed"
  fi
fi

# Run installation script
if [ "$DRY_RUN" = true ]; then
  echo ""
  echo "[DRY RUN] Would run install-data-sync.sh to set up new system"
  echo ""
  echo "=== Dry Run Complete ==="
  echo ""
  echo "To execute migration, run:"
  echo "  sudo bash $(basename $0)"
  exit 0
fi

echo ""
echo "Running installation script..."
bash "$(dirname $0)/install-data-sync.sh"

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
echo "  sudo systemctl daemon-reload"
