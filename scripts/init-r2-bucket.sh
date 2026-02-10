#!/bin/bash
set -e

echo "=== Gardener R2 Bucket Initialization ==="
echo ""

# Configuration
BUCKET="gardener-data"
REMOTE="r2-gardener"

# Check if rclone remote exists
if ! rclone listremotes | grep -q "${REMOTE}:"; then
  echo "ERROR: rclone remote '${REMOTE}' not configured"
  echo ""
  echo "Please configure rclone first:"
  echo "  rclone config create ${REMOTE} s3 \\"
  echo "    provider Cloudflare \\"
  echo "    access_key_id <R2_ACCESS_KEY> \\"
  echo "    secret_access_key <R2_SECRET_KEY> \\"
  echo "    endpoint https://<account_id>.r2.cloudflarestorage.com"
  echo ""
  exit 1
fi

echo "✓ rclone remote '${REMOTE}' configured"
echo ""

# Test bucket access
echo "Testing bucket access..."
if ! rclone lsd ${REMOTE}:${BUCKET} >/dev/null 2>&1; then
  echo "ERROR: Cannot access bucket '${BUCKET}'"
  echo ""
  echo "Please verify:"
  echo "  1. Bucket exists in Cloudflare dashboard"
  echo "  2. API token has correct permissions"
  echo "  3. Endpoint URL is correct"
  echo ""
  exit 1
fi

echo "✓ Bucket '${BUCKET}' accessible"
echo ""

# Initialize folder structure
echo "Initializing bucket structure..."
echo ""

# Create initial manifest
echo "1. Creating initial manifest..."
echo '{"timestamp": null, "scan_time": null, "files": {}}' | \
  rclone rcat ${REMOTE}:${BUCKET}/manifests/current.json
echo "   ✓ manifests/current.json"

# Create empty summaries
echo "2. Creating summary files..."
echo '{}' | rclone rcat ${REMOTE}:${BUCKET}/summaries/daily-metrics.json
echo "   ✓ summaries/daily-metrics.json"

echo '{}' | rclone rcat ${REMOTE}:${BUCKET}/summaries/tool-usage.json
echo "   ✓ summaries/tool-usage.json"

echo '{"photos": []}' | rclone rcat ${REMOTE}:${BUCKET}/summaries/photo-index.json
echo "   ✓ summaries/photo-index.json"

echo '{}' | rclone rcat ${REMOTE}:${BUCKET}/summaries/conversation-index.json
echo "   ✓ summaries/conversation-index.json"

echo '{"deletions": []}' | rclone rcat ${REMOTE}:${BUCKET}/summaries/deletion-log.json
echo "   ✓ summaries/deletion-log.json"

# Create folder README placeholders
echo "3. Creating folder structure markers..."
cat <<'EOF' | rclone rcat ${REMOTE}:${BUCKET}/raw/README.md
# Raw Data Directory

This directory contains all raw data files organized by type and date:

- `photos/YYYY/MM/DD/` - Plant photos (39/day)
- `claude_transcripts/YYYY/MM/DD/` - Claude execution transcripts (148/day)
- `logs/YYYY/MM/DD/` - Agent logs (60/day)
- `notes_archive/YYYY/MM/DD/` - Archived notes (56/day)
- `data/` - JSONL data files (append-only)
- `workspace/` - Workspace files

Files are never deleted, only marked as deleted in manifest.
EOF
echo "   ✓ raw/README.md"

cat <<'EOF' | rclone rcat ${REMOTE}:${BUCKET}/deltas/README.md
# Delta Logs Directory

This directory contains change events from each sync run:

- Organized by month: `YYYY-MM/`
- Each sync creates a timestamped file: `YYYY-MM-DDTHH:MM:SSZ-changes.json`
- Records created, modified, and deleted files
- Enables full audit trail and change data capture (CDC)
- Never modified or deleted after creation

Used by GitHub Actions to incrementally update summaries.
EOF
echo "   ✓ deltas/README.md"

echo ""
echo "=== Initialization Complete ==="
echo ""

# Verify structure
echo "Bucket structure:"
rclone tree ${REMOTE}:${BUCKET} --dirs-only --level 2

echo ""
echo "File count:"
rclone ls ${REMOTE}:${BUCKET} | wc -l | awk '{print $1 " files created"}'

echo ""
echo "Next steps:"
echo "  1. Deploy sync script to Pi"
echo "  2. Configure rclone on Pi as gardener-publisher user"
echo "  3. Run: sudo ./static_site_generator/deploy/install-r2-sync.sh"
