#!/bin/bash
set -e

STAGING_DIR="/home/gardener-publisher/gardener-site"
cd "$STAGING_DIR"

# Configure git user if not already set
if ! git config user.email >/dev/null 2>&1 || ! git config user.name >/dev/null 2>&1; then
  git config user.email "gardener@raspberrypi"
  git config user.name "Claude the Gardener Bot"
fi

echo "[$(date)] Starting data sync..."

# Validate source paths
if [ ! -d "/home/mcpserver/data" ]; then
  echo "WARNING: /home/mcpserver/data not found - skipping data sync"
fi
if [ ! -d "/home/mcpserver/photos" ]; then
  echo "WARNING: /home/mcpserver/photos not found - skipping photos sync"
fi

# Sync all data sources (--no-delete preserves history)
rsync -av --no-delete /home/mcpserver/data/ data/ 2>/dev/null || echo "Skipped: /home/mcpserver/data/"
rsync -av --no-delete /home/mcpserver/photos/ photos/ 2>/dev/null || echo "Skipped: /home/mcpserver/photos/"
rsync -av --no-delete /home/gardener/.claude/ data/claude/ 2>/dev/null || echo "Skipped: /home/gardener/.claude/"
rsync -av --no-delete /home/gardener/workspace/ workspace/ 2>/dev/null || echo "Skipped: /home/gardener/workspace/"
rsync -av --no-delete /home/gardener/logs/ logs/ 2>/dev/null || echo "Skipped: /home/gardener/logs/"

# Pull remote changes before committing
if ! git pull --rebase origin main; then
  echo "ERROR: Failed to pull from remote."
  # Check if we're in a rebase state
  if [ -d ".git/rebase-merge" ] || [ -d ".git/rebase-apply" ]; then
    echo "Aborting rebase..."
    git rebase --abort || true
  fi
  echo "Manual intervention required: cd $STAGING_DIR && git status"
  exit 1
fi

# Commit and push if changes exist
git add data/ photos/ workspace/ logs/ 2>/dev/null || true
if git diff --staged --quiet; then
  echo "No changes detected, skipping push"
  exit 0
fi

git commit -m "Data update $(date -Iseconds)"
if git push origin main; then
  echo "Successfully pushed to GitHub"

  # Clean up old logs on Pi (keep 21 days) if logs directory exists
  if [ -d "/home/gardener/logs" ]; then
    find /home/gardener/logs/ -type f -mtime +21 -delete 2>/dev/null || true
    echo "Cleaned logs older than 21 days from Pi"
  fi
else
  echo "ERROR: Failed to push to GitHub"
  exit 1
fi
