#!/usr/bin/env python3
"""
Sync Pi data to R2 with change detection and minimal SD card writes.

Architecture:
- All temp files in /tmp (tmpfs, no SD writes)
- Change detection via mtime + size (no hashing)
- Uploads only changed files with date-based organization
- Records all changes in delta log for audit trail

Usage:
    python3 sync-to-r2.py [--dry-run]
"""
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Set, Tuple

# Configuration
R2_BUCKET = "gardener-data"
R2_REMOTE = "r2-gardener"  # rclone remote name
TMPFS_DIR = Path("/tmp")  # tmpfs - no SD writes!

# Data sources on Pi
SOURCES = {
    "photos": Path("/home/mcpserver/photos"),
    "claude_transcripts": Path("/home/gardener/.claude/projects/-home-gardener-workspace"),
    "logs": Path("/home/gardener/logs"),
    "notes_archive": Path("/home/mcpserver/data/notes_archive"),
    "data": Path("/home/mcpserver/data"),
    "workspace": Path("/home/gardener/workspace"),
}


def main():
    """Main sync orchestration."""
    dry_run = "--dry-run" in sys.argv

    if dry_run:
        print("=== DRY RUN MODE ===")

    print(f"Starting R2 sync at {datetime.now(timezone.utc).isoformat()}")

    # Implementation in next steps
    pass


if __name__ == "__main__":
    main()
