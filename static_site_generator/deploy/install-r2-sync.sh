#!/bin/bash
set -e

echo "=== Gardener R2 Sync Installation ==="
echo ""

# Check if running as root
if [ "$EUID" -ne 0 ]; then
  echo "ERROR: Must run with sudo"
  exit 1
fi

# Configuration
SYNC_USER="gardener-publisher"
INSTALL_DIR="/home/${SYNC_USER}"
SCRIPT_NAME="sync-to-r2.py"
SERVICE_NAME="gardener-r2-sync"

# Check user exists
if ! id "$SYNC_USER" &>/dev/null; then
  echo "ERROR: User $SYNC_USER does not exist"
  exit 1
fi

# Check rclone is installed
if ! command -v rclone &>/dev/null; then
  echo "ERROR: rclone is not installed"
  echo ""
  echo "Install rclone first:"
  echo "  sudo apt update && sudo apt install rclone -y"
  echo ""
  echo "Then run this installer again."
  exit 1
fi

echo "Installing R2 sync for user: $SYNC_USER"
echo ""

# Step 1: Copy sync script and filter file
echo "1. Installing sync script and dependencies..."
cp "$(dirname "$0")/${SCRIPT_NAME}" "${INSTALL_DIR}/"
chmod +x "${INSTALL_DIR}/${SCRIPT_NAME}"
chown "${SYNC_USER}:${SYNC_USER}" "${INSTALL_DIR}/${SCRIPT_NAME}"
echo "   ✓ Script installed: ${INSTALL_DIR}/${SCRIPT_NAME}"

# Copy rclone filter file (required for sync script)
cp "$(dirname "$0")/rclone-filters.txt" "${INSTALL_DIR}/"
chown "${SYNC_USER}:${SYNC_USER}" "${INSTALL_DIR}/rclone-filters.txt"
echo "   ✓ Filter file installed: ${INSTALL_DIR}/rclone-filters.txt"

# Step 2: Install systemd units
echo "2. Installing systemd units..."
cp "$(dirname "$0")/${SERVICE_NAME}.service" /etc/systemd/system/
cp "$(dirname "$0")/${SERVICE_NAME}.timer" /etc/systemd/system/
echo "   ✓ Service installed: /etc/systemd/system/${SERVICE_NAME}.service"
echo "   ✓ Timer installed: /etc/systemd/system/${SERVICE_NAME}.timer"

# Step 3: Reload systemd
echo "3. Reloading systemd..."
systemctl daemon-reload
echo "   ✓ Systemd reloaded"

# Step 4: Check rclone configuration
echo "4. Checking rclone configuration..."
if ! sudo -u "$SYNC_USER" rclone listremotes | grep -q "r2-gardener"; then
  echo "   ⚠ WARNING: rclone remote 'r2-gardener' not configured!"
  echo ""
  echo "   Configure rclone as $SYNC_USER:"
  echo "   $ sudo -u $SYNC_USER rclone config create r2-gardener s3 \\"
  echo "       provider Cloudflare \\"
  echo "       access_key_id <R2_ACCESS_KEY> \\"
  echo "       secret_access_key <R2_SECRET_KEY> \\"
  echo "       endpoint https://<account_id>.r2.cloudflarestorage.com \\"
  echo "       no_check_bucket true"
  echo ""
  echo "   Installation paused. Configure rclone, then run:"
  echo "   $ sudo systemctl enable --now ${SERVICE_NAME}.timer"
  exit 0
fi
echo "   ✓ rclone configured"

# Step 5: Enable and start timer
echo "5. Enabling timer..."
systemctl enable "${SERVICE_NAME}.timer"
systemctl start "${SERVICE_NAME}.timer"
echo "   ✓ Timer enabled and started"

echo ""
echo "=== Installation Complete ==="
echo ""
echo "Status:"
systemctl status "${SERVICE_NAME}.timer" --no-pager
echo ""
echo "Monitor logs:"
echo "  journalctl -u ${SERVICE_NAME} -f"
echo ""
echo "Trigger manual sync:"
echo "  sudo systemctl start ${SERVICE_NAME}.service"
