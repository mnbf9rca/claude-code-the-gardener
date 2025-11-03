#!/bin/bash
set -euo pipefail

# MCP data backup script
# Commits changes to /home/mcpserver/data/ git repository
# Triggered by systemd timer every 15 minutes

DATA_DIR="${DATA_DIR:-/home/mcpserver/data}"
LOG_PREFIX="[$(date -Iseconds)] [MCP-DATA-BACKUP]"

echo "$LOG_PREFIX Starting MCP data backup"

# Validate data directory exists
if [ ! -d "$DATA_DIR" ]; then
    echo "$LOG_PREFIX ERROR: Data directory not found: $DATA_DIR" >&2
    exit 1
fi

cd "$DATA_DIR"

# Initialize git repo if not already initialized (defensive)
if [ ! -d ".git" ]; then
    echo "$LOG_PREFIX Initializing git repository in $DATA_DIR"
    git init
    git config user.name "MCP Server Backup"
    git config user.email "backup@mcpserver.local"
    # Allow group members to access this repo (prevents "dubious ownership" errors)
    git config --local safe.directory '*'

    # Create .gitignore to exclude photos and temp files
    cat > .gitignore <<EOF
# Exclude photos (too large for git)
*.jpg
*.jpeg
*.png

# Exclude temporary files
*.tmp
*.swp
*.log
EOF

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
if git commit -m "MCP data backup: $TIMESTAMP"; then
    echo "$LOG_PREFIX Successfully committed changes"

    # Show summary of what was committed
    git log -1 --stat --oneline

    exit 0
else
    echo "$LOG_PREFIX ERROR: Git commit failed" >&2
    exit 1
fi
