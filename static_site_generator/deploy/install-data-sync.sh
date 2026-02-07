#!/bin/bash
set -e

DRY_RUN=false
if [ "$1" = "--dry-run" ]; then
  DRY_RUN=true
  echo "=== DRY RUN MODE - No changes will be made ==="
  echo ""
fi

REPO_URL="git@github.com:mnbf9rca/gardener-site.git"
SYNC_USER="gardener-publisher"
REPO_DIR="/home/${SYNC_USER}/gardener-site"
SCRIPT_PATH="/home/${SYNC_USER}/push-to-github.sh"
SERVICE_FILE="/etc/systemd/system/gardener-data-sync.service"
TIMER_FILE="/etc/systemd/system/gardener-data-sync.timer"

echo "=== Gardener Data Sync Installation ==="
echo ""

# Check if running as root
if [ "$EUID" -ne 0 ] && [ "$DRY_RUN" = false ]; then
  echo "ERROR: This script must be run as root (use sudo)"
  exit 1
fi

# Verify sync user exists
if ! id "$SYNC_USER" &>/dev/null; then
  echo "ERROR: User $SYNC_USER does not exist"
  echo "This should be the gardener-publisher user with access to data"
  exit 1
fi

# Clone or update repository
if [ -d "$REPO_DIR" ]; then
  echo "✓ Repository already exists at $REPO_DIR"
else
  if [ "$DRY_RUN" = true ]; then
    echo "[DRY RUN] Would clone $REPO_URL to $REPO_DIR"
  else
    echo "Cloning gardener-site repository..."
    sudo -u "$SYNC_USER" git clone "$REPO_URL" "$REPO_DIR"
    echo "✓ Repository cloned"
  fi
fi

# Check for SSH key
SSH_KEY="/home/${SYNC_USER}/.ssh/id_ed25519"
if [ ! -f "$SSH_KEY" ]; then
  if [ "$DRY_RUN" = true ]; then
    echo "[DRY RUN] Would generate SSH key at $SSH_KEY"
    echo "[DRY RUN] Would prompt to add key to GitHub"
  else
    echo "Generating SSH key for GitHub authentication..."
    sudo -u "$SYNC_USER" ssh-keygen -t ed25519 -C "${SYNC_USER}@pi" -f "$SSH_KEY" -N ""
    echo ""
    echo "=== ACTION REQUIRED ==="
    echo "Add this SSH public key to GitHub (Settings > SSH Keys):"
    echo ""
    cat "${SSH_KEY}.pub"
    echo ""
    read -r -p "Press Enter after adding the key to GitHub..."
  fi
else
  echo "✓ SSH key already exists at $SSH_KEY"
fi

# Add GitHub to known_hosts
if [ "$DRY_RUN" = true ]; then
  echo "[DRY RUN] Would add GitHub to known_hosts"
  echo "[DRY RUN] Would test SSH connectivity to GitHub"
else
  echo "Adding GitHub to known_hosts..."
  sudo -u "$SYNC_USER" mkdir -p "/home/${SYNC_USER}/.ssh"
  sudo -u "$SYNC_USER" sh -c "ssh-keyscan github.com >> /home/${SYNC_USER}/.ssh/known_hosts 2>/dev/null"

  # Test SSH connectivity
  echo "Testing GitHub SSH connectivity..."
  if sudo -u "$SYNC_USER" ssh -T git@github.com 2>&1 | grep -q -E "(successfully authenticated|You've successfully)"; then
    echo "✓ GitHub SSH authentication successful"
  else
    echo "WARNING: GitHub SSH authentication may not be working"
    echo "Manual test: sudo -u $SYNC_USER ssh -T git@github.com"
  fi
fi

# Create push script
if [ "$DRY_RUN" = true ]; then
  echo "[DRY RUN] Would create push script at $SCRIPT_PATH"
else
  echo "Creating push-to-github.sh script..."
  cp "$(dirname "$0")/push-to-github.sh" "$SCRIPT_PATH"
  chmod +x "$SCRIPT_PATH"
  chown "${SYNC_USER}:${SYNC_USER}" "$SCRIPT_PATH"
  echo "✓ Push script created at $SCRIPT_PATH"
fi

# Create systemd service
if [ "$DRY_RUN" = true ]; then
  echo "[DRY RUN] Would create systemd service at $SERVICE_FILE"
  echo "[DRY RUN] Would create systemd timer at $TIMER_FILE"
  echo "[DRY RUN] Would reload systemd daemon"
  echo "[DRY RUN] Would enable and start gardener-data-sync.timer"
  echo ""
  echo "=== Dry Run Complete ==="
  echo ""
  echo "To execute installation, run:"
  echo "  sudo bash $(basename "$0")"
  exit 0
fi

echo "Creating systemd service..."
cp "$(dirname "$0")/gardener-data-sync.service" "$SERVICE_FILE"

# Create systemd timer
echo "Creating systemd timer..."
cp "$(dirname "$0")/gardener-data-sync.timer" "$TIMER_FILE"

# Reload systemd
systemctl daemon-reload
echo "✓ Systemd units created"

# Enable and start timer
systemctl enable gardener-data-sync.timer
systemctl start gardener-data-sync.timer
echo "✓ Timer enabled and started"

echo ""
echo "=== Installation Complete ==="
echo ""
echo "Status:"
systemctl status gardener-data-sync.timer --no-pager
echo ""
echo "To monitor logs:"
echo "  journalctl -u gardener-data-sync -f"
echo ""
echo "To trigger manually:"
echo "  sudo systemctl start gardener-data-sync.service"
