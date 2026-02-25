#!/bin/bash
# install-sync.sh — Idempotent installer for the gardener sync infrastructure
# Run as: sudo ./pi/install-sync.sh (from repo root)
#
# Installs:
#   - sync-to-r2.sh to /home/gardener-publisher/
#   - gardener-sync.service + .timer to /etc/systemd/system/
#   - SSH key for gardener-publisher (for GitHub push)
#   - gardener-site git clone at /home/gardener-publisher/gardener-site/
#
# Disables old services:
#   - gardener-r2-sync.service/.timer  (replaced by this)
#   - gardener-data-sync.service/.timer (retired)
#   - gardener-site-publisher.service/.timer (retired)

set -euo pipefail

# Resolve script directory (works even if called from different dir)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Source shared helper functions
# shellcheck source=../scripts/install-helpers.sh
source "${SCRIPT_DIR}/../scripts/install-helpers.sh"

echo "=== Gardener Sync Installation ==="
echo ""

# ═══════════════════════════════════════════════════════
# Pre-flight validation — check everything before making changes
# ═══════════════════════════════════════════════════════

if [ "$EUID" -ne 0 ]; then
    echo "ERROR: Must run with sudo"
    exit 1
fi

SYNC_USER="gardener-publisher"
SYNC_HOME="/home/${SYNC_USER}"
# Reusing the existing gardener-site repo as the workspace repo.
# It's already cloned here with the deploy key wired up.
STAGING_DIR="${SYNC_HOME}/gardener-site"
GITHUB_REPO="git@github.com:mnbf9rca/gardener-site.git"
SERVICE_NAME="gardener-sync"

echo "Checking prerequisites..."

# User exists
if ! id "$SYNC_USER" &>/dev/null; then
    echo "✗ ERROR: User $SYNC_USER does not exist."
    echo "  Run the publisher installer first: sudo ./static_site_generator/deploy/install-publisher.sh"
    exit 1
fi
echo "✓ User $SYNC_USER exists"

# rclone installed
if ! command -v rclone &>/dev/null; then
    echo "✗ ERROR: rclone is not installed."
    echo "  sudo apt update && sudo apt install rclone -y"
    exit 1
fi
echo "✓ rclone $(rclone --version | head -1 | awk '{print $2}')"

# rsync installed (used by sync script for workspace staging)
if ! command -v rsync &>/dev/null; then
    echo "✗ ERROR: rsync is not installed."
    echo "  sudo apt install rsync -y"
    exit 1
fi
echo "✓ rsync $(rsync --version | head -1)"

# git installed (used by sync script to push workspace to GitHub)
if ! command -v git &>/dev/null; then
    echo "✗ ERROR: git is not installed."
    echo "  sudo apt install git -y"
    exit 1
fi
echo "✓ $(git --version)"

# rclone r2-gardener remote configured for sync user
if ! sudo -u "$SYNC_USER" rclone listremotes 2>/dev/null | grep -q "r2-gardener:"; then
    echo "✗ ERROR: rclone remote 'r2-gardener' not configured for $SYNC_USER."
    echo ""
    echo "  Configure rclone as $SYNC_USER:"
    echo "    sudo -u $SYNC_USER rclone config create r2-gardener s3 \\"
    echo "      provider Cloudflare \\"
    echo "      access_key_id YOUR_KEY \\"
    echo "      secret_access_key YOUR_SECRET \\"
    echo "      endpoint https://ACCOUNT_ID.r2.cloudflarestorage.com \\"
    echo "      no_check_bucket true"
    exit 1
fi
echo "✓ rclone remote 'r2-gardener' configured"

# Required source files in repo
REQUIRED_FILES=(
    "${SCRIPT_DIR}/sync-to-r2.sh"
    "${SCRIPT_DIR}/gardener-sync.service"
    "${SCRIPT_DIR}/gardener-sync.timer"
)
MISSING=()
for f in "${REQUIRED_FILES[@]}"; do
    [ -f "$f" ] || MISSING+=("$f")
done
if [ "${#MISSING[@]}" -gt 0 ]; then
    echo "✗ ERROR: Missing required files:"
    printf '  %s\n' "${MISSING[@]}"
    exit 1
fi
echo "✓ All required source files present"
echo ""

# ═══════════════════════════════════════════════════════
# Step 1: Verify SSH key for GitHub push
# ═══════════════════════════════════════════════════════
echo "1. Verifying SSH key for GitHub..."

SSH_DIR="${SYNC_HOME}/.ssh"
SSH_KEY="${SSH_DIR}/id_ed25519"

# The gardener-publisher SSH key was set up during the publisher install.
# It lives at /home/gardener-publisher/.ssh/id_ed25519 (mode 700 dir, 600 key).
# Its deploy key fingerprint: SHA256:m3S/Qz7CLOz2LWbmus2GFL/Fu5mvO9RXGpJX6XvUbQ8
# It must be added as a write-access deploy key on the gardener-site repo.

if [ ! -f "$SSH_KEY" ]; then
    echo "✗ ERROR: SSH key not found at ${SSH_KEY}"
    echo "  The gardener-publisher user is missing its SSH key."
    echo "  Re-run the publisher installer to set it up."
    exit 1
fi
echo "   ✓ SSH key exists at ${SSH_KEY}"

# Pre-populate github.com known_hosts if not already present
if ! sudo -u "$SYNC_USER" ssh-keygen -F github.com &>/dev/null; then
    sudo -u "$SYNC_USER" ssh-keyscan -H github.com 2>/dev/null \
        | sudo -u "$SYNC_USER" tee -a "${SSH_DIR}/known_hosts" > /dev/null || true
    echo "   ✓ github.com added to known_hosts"
fi

# Test GitHub SSH access — the deploy key must be added to gardener-site repo
# Use StrictHostKeyChecking=yes so the known_hosts entry just populated is enforced
if sudo -u "$SYNC_USER" \
        ssh -T \
        -o StrictHostKeyChecking=yes \
        -o ConnectTimeout=10 \
        git@github.com 2>&1 | grep -q "successfully authenticated"; then
    echo "   ✓ GitHub SSH authentication works"
else
    echo ""
    echo "   ⚠  Cannot authenticate to GitHub as $SYNC_USER."
    echo "   Add this user's deploy key to the gardener-site repo:"
    echo "   https://github.com/mnbf9rca/gardener-site/settings/keys"
    echo "   (tick 'Allow write access')"
    echo ""
    echo "   Current public key:"
    cat "${SSH_KEY}.pub" 2>/dev/null || echo "   (cannot read)"
    echo ""
    read -rp "   Continue anyway? [y/N]: " REPLY
    [[ "$REPLY" =~ ^[Yy]$ ]] || exit 1
fi
echo ""

# ═══════════════════════════════════════════════════════
# Step 2: Workspace staging directory (reuses existing gardener-site clone)
# ═══════════════════════════════════════════════════════
echo "2. Workspace staging directory..."

# The gardener-site repo must already be cloned and have its history reset
# (orphan commit) BEFORE running this installer. See pre-flight manual steps.
if [ ! -d "${STAGING_DIR}/.git" ]; then
    echo "✗ ERROR: Expected git repo at ${STAGING_DIR} — not found."
    echo "  Complete the pre-flight steps first (see plan pre-flight section)."
    exit 1
fi

# Verify the remote points to the right repo
ACTUAL_REMOTE=$(sudo -u "$SYNC_USER" git -C "$STAGING_DIR" remote get-url origin 2>/dev/null || echo "")
if [ "$ACTUAL_REMOTE" != "$GITHUB_REPO" ]; then
    echo "✗ ERROR: Remote origin is '${ACTUAL_REMOTE}', expected '${GITHUB_REPO}'"
    exit 1
fi
echo "   ✓ Staging dir at ${STAGING_DIR} (remote: ${GITHUB_REPO})"

# Set git identity (idempotent — git config simply overwrites)
sudo -u "$SYNC_USER" git -C "$STAGING_DIR" config user.email "gardener-publisher@raspberrypi"
sudo -u "$SYNC_USER" git -C "$STAGING_DIR" config user.name "Claude the Gardener Bot"
echo "   ✓ Git identity configured"

# Prevent "dubious ownership" errors for any sudo/rob access
add_safe_directory "$STAGING_DIR"
echo ""

# ═══════════════════════════════════════════════════════
# Step 3: Install sync script
# ═══════════════════════════════════════════════════════
echo "3. Installing sync script..."

install -m 750 -o "${SYNC_USER}" -g "${SYNC_USER}" \
    "${SCRIPT_DIR}/sync-to-r2.sh" \
    "${SYNC_HOME}/sync-to-r2.sh"

echo "   ✓ ${SYNC_HOME}/sync-to-r2.sh"
echo ""

# ═══════════════════════════════════════════════════════
# Step 4: Install systemd units
# ═══════════════════════════════════════════════════════
echo "4. Installing systemd units..."

cp "${SCRIPT_DIR}/gardener-sync.service" /etc/systemd/system/
cp "${SCRIPT_DIR}/gardener-sync.timer"   /etc/systemd/system/
systemctl daemon-reload

echo "   ✓ /etc/systemd/system/gardener-sync.service"
echo "   ✓ /etc/systemd/system/gardener-sync.timer"
echo ""

# ═══════════════════════════════════════════════════════
# Step 5: Disable old services
# ═══════════════════════════════════════════════════════
echo "5. Disabling old sync services..."

OLD_UNITS=(
    "gardener-r2-sync.timer"
    "gardener-r2-sync.service"
    "gardener-data-sync.timer"
    "gardener-data-sync.service"
    "gardener-site-publisher.timer"
    "gardener-site-publisher.service"
)
for unit in "${OLD_UNITS[@]}"; do
    if ! systemctl list-unit-files "$unit" 2>/dev/null | grep -q "$unit"; then
        echo "   - $unit not found, skipping"
        continue
    fi
    if systemctl is-active --quiet "$unit" 2>/dev/null; then
        systemctl stop "$unit"
        echo "   ✓ Stopped $unit"
    fi
    if systemctl is-enabled --quiet "$unit" 2>/dev/null; then
        systemctl disable "$unit"
        echo "   ✓ Disabled $unit"
    fi
done
echo ""

# ═══════════════════════════════════════════════════════
# Step 6: Enable and start new timer
# ═══════════════════════════════════════════════════════
echo "6. Enabling gardener-sync.timer..."

systemctl enable "${SERVICE_NAME}.timer"
systemctl start  "${SERVICE_NAME}.timer"

echo "   ✓ Timer enabled and started"
echo ""

# ═══════════════════════════════════════════════════════
# Done
# ═══════════════════════════════════════════════════════
echo "=== Installation Complete ==="
echo ""
echo "Timer status:"
systemctl status "${SERVICE_NAME}.timer" --no-pager -l
echo ""
echo "Trigger a manual sync now:"
echo "  sudo systemctl start ${SERVICE_NAME}.service"
echo ""
echo "Watch logs:"
echo "  journalctl -u ${SERVICE_NAME} -f"
echo ""
echo "Verify R2 data:"
echo "  sudo -u ${SYNC_USER} rclone ls r2-gardener:gardener-data/raw/data/ | head -20"
echo "  sudo -u ${SYNC_USER} rclone ls r2-gardener:gardener-data/raw/sessions/ | wc -l"
