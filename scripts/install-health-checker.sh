#!/bin/bash
# Install Starship OS Agent Health Checker service
set -e

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
SERVICE_NAME="starship-health-checker"

echo "=== Installing $SERVICE_NAME service ==="

# Copy systemd unit
sudo cp "$REPO_DIR/systemd/$SERVICE_NAME.service" "/etc/systemd/system/$SERVICE_NAME.service"
sudo systemctl daemon-reload

# Ensure health status directory exists
sudo mkdir -p /var/lib/starship
sudo chmod 755 /var/lib/starship

# Enable and start
sudo systemctl enable "$SERVICE_NAME"
sudo systemctl restart "$SERVICE_NAME" 2>/dev/null || sudo systemctl start "$SERVICE_NAME"

echo ""
echo "=== Status ==="
sudo systemctl status "$SERVICE_NAME" --no-pager || true
echo ""
echo "=== Logs ==="
echo "  journalctl -u $SERVICE_NAME -f"
