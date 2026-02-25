#!/bin/bash
# uninstall-old-services.sh — Remove retired gardener services and their artifacts
# Run as: sudo ./pi/uninstall-old-services.sh (from repo root)
#
# Removes:
#   - gardener-site-publisher.service/.timer  (old static site generator)
#   - gardener-data-sync.service/.timer       (old git-based MCP data backup)
#   - gardener-r2-sync.service/.timer         (old R2 sync, replaced by gardener-sync)
#
# Cleans up artifacts:
#   - /home/mcpserver/data/.git               (8.6G git history, data in R2)
#   - /home/gardener/claude-backup/           (3.4G, sessions in R2 via gardener-sync)
#   - /home/gardener-publisher/app/output/    (5G rendered output, service is dead)
#
# Idempotent: safe to run multiple times. Skips anything already gone.

set -euo pipefail

if [ "$EUID" -ne 0 ]; then
    echo "ERROR: Must run with sudo"
    exit 1
fi

echo "=== Gardener Old Services Cleanup ==="
echo ""

# ═══════════════════════════════════════════════════════
# Step 1: Remove old systemd units
# ═══════════════════════════════════════════════════════
echo "1. Removing old systemd units..."

OLD_UNITS=(
    "gardener-site-publisher.timer"
    "gardener-site-publisher.service"
    "gardener-data-sync.timer"
    "gardener-data-sync.service"
    "gardener-r2-sync.timer"
    "gardener-r2-sync.service"
)

removed_any=false
for unit in "${OLD_UNITS[@]}"; do
    unit_file="/etc/systemd/system/${unit}"

    if ! systemctl list-unit-files "$unit" 2>/dev/null | grep -q "$unit"; then
        echo "   - ${unit}: not installed, skipping"
        continue
    fi

    if systemctl is-active --quiet "$unit" 2>/dev/null; then
        systemctl stop "$unit"
        echo "   ✓ Stopped ${unit}"
    fi

    if systemctl is-enabled --quiet "$unit" 2>/dev/null; then
        systemctl disable "$unit"
        echo "   ✓ Disabled ${unit}"
    fi

    if [ -f "$unit_file" ]; then
        rm "$unit_file"
        echo "   ✓ Removed ${unit_file}"
        removed_any=true
    fi
done

if "$removed_any"; then
    systemctl daemon-reload
    echo "   ✓ systemctl daemon-reload"
fi
echo ""

# ═══════════════════════════════════════════════════════
# Step 2: Remove mcpserver/data/.git
#   8.6G of git history from the old backup-mcp-data.sh
#   which committed JSONL files every 30 minutes Nov 3–28 2025.
#   The data files themselves are retained; only the git history is removed.
#   All data is in R2 via gardener-sync.
# ═══════════════════════════════════════════════════════
echo "2. Removing /home/mcpserver/data/.git..."

if [ -d "/home/mcpserver/data/.git" ]; then
    size=$(du -sh /home/mcpserver/data/.git 2>/dev/null | cut -f1)
    rm -rf /home/mcpserver/data/.git
    echo "   ✓ Removed (freed ~${size})"
else
    echo "   - Already gone, skipping"
fi
echo ""

# ═══════════════════════════════════════════════════════
# Step 3: Remove /home/gardener/claude-backup/
#   3.4G local git backup of Claude session JSONL files.
#   Superseded by gardener-sync which uploads sessions to
#   R2 at gardener-data/raw/sessions/YYYY/MM/DD/.
# ═══════════════════════════════════════════════════════
echo "3. Removing /home/gardener/claude-backup/..."

if [ -d "/home/gardener/claude-backup" ]; then
    size=$(du -sh /home/gardener/claude-backup 2>/dev/null | cut -f1)
    rm -rf /home/gardener/claude-backup
    echo "   ✓ Removed (freed ~${size})"
else
    echo "   - Already gone, skipping"
fi
echo ""

# ═══════════════════════════════════════════════════════
# Step 4: Remove /home/gardener-publisher/app/output/
#   5G of rendered HTML and photo copies from the old
#   static site generator. Service is disabled; the new
#   Astro site is built in GitHub Actions.
# ═══════════════════════════════════════════════════════
echo "4. Removing /home/gardener-publisher/app/output/..."

if [ -d "/home/gardener-publisher/app/output" ]; then
    size=$(du -sh /home/gardener-publisher/app/output 2>/dev/null | cut -f1)
    rm -rf /home/gardener-publisher/app/output
    echo "   ✓ Removed (freed ~${size})"
else
    echo "   - Already gone, skipping"
fi
echo ""

# ═══════════════════════════════════════════════════════
# Done
# ═══════════════════════════════════════════════════════
echo "=== Cleanup complete ==="
df -h /dev/mmcblk0p2 2>/dev/null || df -h /
