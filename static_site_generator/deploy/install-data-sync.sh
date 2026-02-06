#!/bin/bash
set -e

REPO_URL="https://github.com/mnbf9rca/gardener-site.git"
REPO_DIR="/home/gardener/gardener-site"
SCRIPT_PATH="/home/gardener/push-to-github.sh"
SERVICE_FILE="/etc/systemd/system/gardener-data-sync.service"
TIMER_FILE="/etc/systemd/system/gardener-data-sync.timer"

echo "=== Gardener Data Sync Installation ==="
echo ""

# Check if running as root
if [ "$EUID" -ne 0 ]; then
  echo "ERROR: This script must be run as root (use sudo)"
  exit 1
fi

# Clone or update repository
if [ -d "$REPO_DIR" ]; then
  echo "✓ Repository already exists at $REPO_DIR"
else
  echo "Cloning gardener-site repository..."
  sudo -u gardener git clone "$REPO_URL" "$REPO_DIR"
  echo "✓ Repository cloned"
fi

# Check for SSH key
SSH_KEY="/home/gardener/.ssh/id_ed25519"
if [ ! -f "$SSH_KEY" ]; then
  echo "Generating SSH key for GitHub authentication..."
  sudo -u gardener ssh-keygen -t ed25519 -C "gardener@pi" -f "$SSH_KEY" -N ""
  echo ""
  echo "=== ACTION REQUIRED ==="
  echo "Add this SSH public key to GitHub (Settings > SSH Keys):"
  echo ""
  cat "${SSH_KEY}.pub"
  echo ""
  read -p "Press Enter after adding the key to GitHub..."
fi

# Test SSH connectivity
echo "Testing GitHub SSH connectivity..."
if sudo -u gardener ssh -T git@github.com 2>&1 | grep -q "successfully authenticated"; then
  echo "✓ GitHub SSH authentication successful"
else
  echo "WARNING: GitHub SSH authentication may not be working"
  echo "Manual test: sudo -u gardener ssh -T git@github.com"
fi

# Create push script
echo "Creating push-to-github.sh script..."
cat > "$SCRIPT_PATH" << 'EOF'
#!/bin/bash
set -e

STAGING_DIR="/home/gardener/gardener-site"
cd "$STAGING_DIR"

echo "[$(date)] Starting data sync..."

# Sync all data sources (--no-delete preserves history)
rsync -av --no-delete /home/mcpserver/data/ data/ || true
rsync -av --no-delete /home/mcpserver/photos/ photos/ || true
rsync -av --no-delete /home/gardener/.claude/ data/claude/ || true
rsync -av --no-delete /home/gardener/workspace/ workspace/ || true
rsync -av --no-delete /home/gardener/logs/ logs/ || true

# Commit and push if changes exist
git add data/ photos/ workspace/ logs/ 2>/dev/null || true
if git diff --staged --quiet; then
  echo "No changes detected, skipping push"
  exit 0
fi

git commit -m "Data update $(date -Iseconds)"
if git push origin main; then
  echo "Successfully pushed to GitHub"

  # Clean up old logs on Pi (keep 21 days)
  find /home/gardener/logs/ -type f -mtime +21 -delete 2>/dev/null || true
  echo "Cleaned logs older than 21 days from Pi"
else
  echo "ERROR: Failed to push to GitHub"
  exit 1
fi
EOF

chmod +x "$SCRIPT_PATH"
chown gardener:gardener "$SCRIPT_PATH"
echo "✓ Push script created at $SCRIPT_PATH"

# Create systemd service
echo "Creating systemd service..."
cat > "$SERVICE_FILE" << EOF
[Unit]
Description=Gardener Data Sync to GitHub
After=network.target

[Service]
Type=oneshot
User=gardener
WorkingDirectory=/home/gardener
ExecStart=$SCRIPT_PATH
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

# Create systemd timer
echo "Creating systemd timer..."
cat > "$TIMER_FILE" << EOF
[Unit]
Description=Run Gardener Data Sync every 15 minutes

[Timer]
OnBootSec=5min
OnUnitActiveSec=15min
AccuracySec=1min

[Install]
WantedBy=timers.target
EOF

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
