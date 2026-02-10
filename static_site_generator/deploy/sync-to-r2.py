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


def download_manifest() -> Dict:
    """
    Download current manifest from R2 to tmpfs.

    Returns empty manifest if file doesn't exist yet (first run).
    """
    manifest_path = TMPFS_DIR / "current-manifest.json"

    # Download from R2
    result = subprocess.run(
        [
            "rclone", "copyto",
            f"{R2_REMOTE}:{R2_BUCKET}/manifests/current.json",
            str(manifest_path)
        ],
        capture_output=True,
        text=True
    )

    # If file doesn't exist (first run), return empty manifest
    if result.returncode != 0:
        print("No existing manifest found (first sync)")
        return {"timestamp": None, "files": {}}

    # Parse manifest
    try:
        with manifest_path.open('r') as f:
            manifest = json.load(f)
        print(f"✓ Downloaded manifest: {len(manifest.get('files', {}))} files")
        return manifest
    except json.JSONDecodeError as e:
        print(f"ERROR: Corrupt manifest: {e}")
        sys.exit(1)


def scan_filesystem() -> Dict:
    """
    Scan current Pi filesystem state.

    Uses mtime + size for change detection (no expensive hashing).
    Reads from mounted directories, no SD writes.

    Returns manifest dict with all current files.
    """
    files = {}
    scanned_count = 0

    for source_name, source_path in SOURCES.items():
        if not source_path.exists():
            print(f"  ⚠ Skipping {source_name}: path not found")
            continue

        print(f"  Scanning {source_name}...", end=" ", flush=True)
        source_file_count = 0

        # Recursively scan all files
        for file_path in source_path.rglob("*"):
            if not file_path.is_file():
                continue

            # Skip .git directories entirely
            if '.git' in file_path.parts:
                continue

            # Skip other hidden files/directories except .claude
            parts_list = list(file_path.parts)
            if any(part.startswith('.') and part != '.claude' for part in parts_list):
                continue

            try:
                stat = file_path.stat()
                rel_path = str(file_path.relative_to(source_path))
                file_key = f"{source_name}/{rel_path}"

                files[file_key] = {
                    "size": stat.st_size,
                    "mtime": stat.st_mtime,
                }

                source_file_count += 1
                scanned_count += 1

            except (PermissionError, OSError) as e:
                print(f"\n  ⚠ Cannot read {file_path}: {e}")
                continue

        print(f"{source_file_count} files")

    return {
        "timestamp": time.time(),
        "scan_time": datetime.now(timezone.utc).isoformat(),
        "files": files
    }


def detect_changes(old_manifest: Dict, new_manifest: Dict) -> Dict:
    """
    Detect changes between old and new manifests.

    Uses mtime and size to identify modifications.
    Files missing from new manifest are marked as deleted.

    Returns dict with created, modified, deleted file lists.
    """
    old_files = set(old_manifest.get("files", {}).keys())
    new_files = set(new_manifest["files"].keys())

    # Files in new but not old = created
    created = new_files - old_files

    # Files in old but not new = deleted
    deleted = old_files - new_files

    # Files in both - check if modified
    potentially_modified = old_files & new_files
    last_sync_time = old_manifest.get("timestamp", 0) or 0

    modified = set()
    for file_key in potentially_modified:
        old_info = old_manifest["files"][file_key]
        new_info = new_manifest["files"][file_key]

        # Modified if: mtime newer than last sync OR size changed
        if (new_info["mtime"] > last_sync_time or
            new_info["size"] != old_info["size"]):
            modified.add(file_key)

    return {
        "created": sorted(created),
        "modified": sorted(modified),
        "deleted": sorted(deleted),
        "total": len(created) + len(modified) + len(deleted)
    }


def main():
    """Main sync orchestration."""
    dry_run = "--dry-run" in sys.argv

    if dry_run:
        print("=== DRY RUN MODE ===")

    print(f"Starting R2 sync at {datetime.now(timezone.utc).isoformat()}")

    # Step 1: Download current manifest
    old_manifest = download_manifest()
    print(f"Manifest loaded: {old_manifest.get('timestamp', 'Never synced')}")

    # Step 2: Scan current filesystem
    print("\nScanning filesystem:")
    new_manifest = scan_filesystem()
    print(f"✓ Scan complete: {len(new_manifest['files'])} files found")

    # Step 3: Detect changes
    print("\nDetecting changes...")
    changes = detect_changes(old_manifest, new_manifest)

    print(f"  Created: {len(changes['created'])} files")
    print(f"  Modified: {len(changes['modified'])} files")
    print(f"  Deleted: {len(changes['deleted'])} files")
    print(f"  Total changes: {changes['total']}")

    if changes['total'] == 0:
        print("\n✓ No changes detected")
        return


if __name__ == "__main__":
    main()
