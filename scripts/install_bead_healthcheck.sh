#!/usr/bin/env bash
# Installation script for bead health check systemd timer

set -euo pipefail

SERVICE_NAME="bead-healthcheck"
WORKSPACE_DIR="/home/coding/aide-de-camp"
SERVICE_FILE="$WORKSPACE_DIR/deploy/$SERVICE_NAME.service"
TIMER_FILE="$WORKSPACE_DIR/deploy/$SERVICE_NAME.timer"
SYSTEMD_DIR="$HOME/.config/systemd/user"

echo "=== Installing Bead Health Check Timer ==="

# Create systemd user directory if it doesn't exist
mkdir -p "$SYSTEMD_DIR"

# Link service and timer files
echo "Linking service file..."
ln -sf "$SERVICE_FILE" "$SYSTEMD_DIR/$SERVICE_NAME.service"

echo "Linking timer file..."
ln -sf "$TIMER_FILE" "$SYSTEMD_DIR/$SERVICE_NAME.timer"

# Reload systemd daemon
echo "Reloading systemd daemon..."
systemctl --user daemon-reload

# Enable and start the timer
echo "Enabling and starting timer..."
systemctl --user enable "$SERVICE_NAME.timer"
systemctl --user start "$SERVICE_NAME.timer"

# Show status
echo ""
echo "=== Installation Complete ==="
echo "Timer status:"
systemctl --user status "$SERVICE_NAME.timer" --no-pager

echo ""
echo "Next scheduled runs:"
systemctl --user list-timers "$SERVICE_NAME.timer" --no-pager

echo ""
echo "To view logs: tail -f /tmp/bead-healthcheck.log"
echo "To disable: systemctl --user disable $SERVICE_NAME.timer --now"
