#!/bin/bash
set -euo pipefail

# MCP photos backup script
# Commits changes to /home/mcpserver/photos/ git repository
# Triggered by systemd timer every 15 minutes

PHOTOS_DIR="${PHOTOS_DIR:-/home/mcpserver/photos}"
LOG_PREFIX="[$(date -Iseconds)] [MCP-PHOTOS-BACKUP]"

echo "$LOG_PREFIX Starting MCP photos backup"

# Validate photos directory exists
if [ ! -d "$PHOTOS_DIR" ]; then
    echo "$LOG_PREFIX ERROR: Photos directory not found: $PHOTOS_DIR" >&2
    exit 1
fi

cd "$PHOTOS_DIR"

# Initialize git repo if not already initialized (defensive)
if [ ! -d ".git" ]; then
    echo "$LOG_PREFIX Initializing git repository in $PHOTOS_DIR"
    git init --initial-branch=main
    git config user.name "MCP Photos Backup"
    git config user.email "backup@mcpserver.local"

    echo "$LOG_PREFIX Git repository initialized"
fi

# Add all changes
git add -A

# Check if there are changes to commit
if git diff --cached --quiet; then
    echo "$LOG_PREFIX No changes detected, skipping commit"
    exit 0
fi

# Commit with timestamp
TIMESTAMP=$(date -Iseconds)
if git commit -m "MCP photos backup: $TIMESTAMP"; then
    echo "$LOG_PREFIX Successfully committed changes"

    # Show summary of what was committed
    git log -1 --stat --oneline

    exit 0
else
    echo "$LOG_PREFIX ERROR: Git commit failed" >&2
    exit 1
fi
