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


def get_r2_path(file_key: str) -> str:
    """
    Map file key to R2 path with date-based hierarchy.

    High-volume sources (photos, transcripts, logs, notes) get day-level folders.
    Low-volume sources (data, workspace) stay flat.

    Examples:
        photos/plant_123.jpg → raw/photos/2026/02/10/plant_123.jpg
        data/action_log.jsonl → raw/data/action_log.jsonl
    """
    source, rel_path = file_key.split("/", 1)
    filename = Path(rel_path).name

    # High-volume sources get date hierarchy
    if source in ["photos", "claude_transcripts", "logs", "notes_archive"]:
        today = datetime.now(timezone.utc)
        date_path = f"{today.year:04d}/{today.month:02d}/{today.day:02d}"
        return f"raw/{source}/{date_path}/{filename}"
    else:
        # Low-volume sources stay flat
        return f"raw/{source}/{rel_path}"


def get_local_path(file_key: str) -> Path:
    """
    Map file key back to local filesystem path.

    Example:
        photos/plant_123.jpg → /home/mcpserver/photos/plant_123.jpg
    """
    source, rel_path = file_key.split("/", 1)
    source_path = SOURCES.get(source)

    if not source_path:
        raise ValueError(f"Unknown source: {source}")

    return source_path / rel_path


def upload_file(file_key: str, dry_run: bool = False) -> bool:
    """
    Upload single file to R2.

    Returns True if successful, False otherwise.
    """
    try:
        local_path = get_local_path(file_key)
        r2_path = get_r2_path(file_key)
        r2_full_path = f"{R2_REMOTE}:{R2_BUCKET}/{r2_path}"

        if dry_run:
            print(f"  [DRY RUN] Would upload: {file_key} → {r2_path}")
            return True

        # Upload with rclone
        result = subprocess.run(
            ["rclone", "copyto", str(local_path), r2_full_path],
            capture_output=True,
            text=True
        )

        if result.returncode != 0:
            print(f"  ✗ Failed: {file_key}")
            print(f"    Error: {result.stderr}")
            return False

        return True

    except Exception as e:
        print(f"  ✗ Error uploading {file_key}: {e}")
        return False


def upload_changes(changes: Dict, dry_run: bool = False) -> Dict:
    """
    Upload all new and modified files to R2.

    Returns summary of upload results.
    """
    files_to_upload = changes["created"] + changes["modified"]

    if not files_to_upload:
        return {"uploaded": 0, "failed": 0}

    print(f"\nUploading {len(files_to_upload)} files...")

    uploaded = 0
    failed = 0

    for file_key in files_to_upload:
        if upload_file(file_key, dry_run):
            uploaded += 1
        else:
            failed += 1

        # Progress indicator every 10 files
        if (uploaded + failed) % 10 == 0:
            print(f"  Progress: {uploaded + failed}/{len(files_to_upload)}")

    return {"uploaded": uploaded, "failed": failed}


def record_deltas(changes: Dict, new_manifest: Dict, dry_run: bool = False):
    """
    Record change events to R2 delta log.

    Creates timestamped delta file with all changes for this sync.
    Enables full audit trail and change data capture (CDC).
    """
    if changes['total'] == 0:
        return  # No changes to record

    timestamp = datetime.now(timezone.utc)
    iso_timestamp = timestamp.isoformat()

    # Build delta events
    events = []

    # Created files
    for file_key in changes['created']:
        file_info = new_manifest['files'][file_key]
        events.append({
            "type": "created",
            "path": file_key,
            "timestamp": iso_timestamp,
            "size": file_info["size"],
            "mtime": file_info["mtime"],
            "r2_path": get_r2_path(file_key)
        })

    # Modified files
    for file_key in changes['modified']:
        file_info = new_manifest['files'][file_key]
        events.append({
            "type": "modified",
            "path": file_key,
            "timestamp": iso_timestamp,
            "size": file_info["size"],
            "mtime": file_info["mtime"],
            "r2_path": get_r2_path(file_key)
        })

    # Deleted files (file missing from Pi, mark in R2)
    for file_key in changes['deleted']:
        events.append({
            "type": "deleted",
            "path": file_key,
            "detected_at": iso_timestamp,
            "reason": "missing_from_pi",
            "note": "File remains in R2, marked as deleted in manifest"
        })

    delta_data = {
        "sync_timestamp": iso_timestamp,
        "events": events,
        "summary": {
            "created": len(changes['created']),
            "modified": len(changes['modified']),
            "deleted": len(changes['deleted'])
        }
    }

    # Upload delta log
    delta_filename = f"{timestamp.strftime('%Y-%m-%dT%H:%M:%S')}Z-changes.json"
    delta_path = f"deltas/{timestamp.strftime('%Y-%m')}/{delta_filename}"
    r2_delta_path = f"{R2_REMOTE}:{R2_BUCKET}/{delta_path}"

    if dry_run:
        print(f"\n[DRY RUN] Would record delta log: {delta_path}")
        print(f"  Events: {len(events)}")
        return

    print(f"\nRecording delta log: {delta_path}")

    # Upload via rclone rcat (stdin)
    delta_json = json.dumps(delta_data, indent=2)
    result = subprocess.run(
        ["rclone", "rcat", r2_delta_path],
        input=delta_json.encode(),
        capture_output=True
    )

    if result.returncode != 0:
        print(f"  ⚠ Failed to record delta: {result.stderr.decode()}")
    else:
        print(f"  ✓ Delta recorded: {len(events)} events")


def upload_manifest(manifest: Dict, dry_run: bool = False):
    """
    Upload updated manifest to R2.

    Becomes the new current.json for next sync.
    """
    manifest_path = f"{R2_REMOTE}:{R2_BUCKET}/manifests/current.json"

    if dry_run:
        print(f"\n[DRY RUN] Would upload updated manifest")
        print(f"  Files tracked: {len(manifest.get('files', {}))}")
        return

    print(f"\nUploading updated manifest...")

    # Upload via rclone rcat
    manifest_json = json.dumps(manifest, indent=2)
    result = subprocess.run(
        ["rclone", "rcat", manifest_path],
        input=manifest_json.encode(),
        capture_output=True
    )

    if result.returncode != 0:
        print(f"  ✗ Failed to upload manifest: {result.stderr.decode()}")
        sys.exit(1)

    print(f"  ✓ Manifest uploaded: {len(manifest['files'])} files tracked")


def main():
    """Main sync orchestration."""
    dry_run = "--dry-run" in sys.argv
    start_time = time.time()

    if dry_run:
        print("=== DRY RUN MODE ===")

    print(f"Starting R2 sync at {datetime.now(timezone.utc).isoformat()}")

    try:
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

        # Step 4: Upload new and modified files
        upload_results = upload_changes(changes, dry_run)

        # Step 5: Record delta events
        record_deltas(changes, new_manifest, dry_run)

        # Step 6: Upload updated manifest
        upload_manifest(new_manifest, dry_run)

        # Final summary
        elapsed = time.time() - start_time
        print(f"\n{'='*50}")
        print(f"✓ Sync complete in {elapsed:.1f}s")
        print(f"  Uploaded: {upload_results['uploaded']} files")
        if upload_results['failed'] > 0:
            print(f"  Failed: {upload_results['failed']} files")
        print(f"  Delta recorded: {changes['total']} events")
        print(f"{'='*50}")

    except KeyboardInterrupt:
        print("\n\nSync interrupted by user")
        sys.exit(130)
    except Exception as e:
        print(f"\n✗ Sync failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
