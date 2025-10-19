#!/bin/bash
# OK Monitor Device Update Script
# Automatically pulls latest code and restarts the service

set -e

INSTALL_DIR="/opt/okmonitor"
SERVICE_NAME="okmonitor-device"
LOG_FILE="/var/log/okmonitor-update.log"

# Logging function
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

log "===== Starting OK Monitor device update ====="

# Change to install directory
cd "$INSTALL_DIR" || {
    log "ERROR: Failed to change to $INSTALL_DIR"
    exit 1
}

# Check if git repository
if [ ! -d ".git" ]; then
    log "ERROR: Not a git repository. Skipping update."
    exit 1
fi

# Stash any local changes
log "Stashing local changes (if any)..."
sudo -u pi git stash

# Fetch latest changes
log "Fetching latest changes from remote..."
sudo -u pi git fetch origin

# Get current and remote commit hashes
CURRENT_COMMIT=$(sudo -u pi git rev-parse HEAD)
REMOTE_COMMIT=$(sudo -u pi git rev-parse origin/deployment)

if [ "$CURRENT_COMMIT" = "$REMOTE_COMMIT" ]; then
    log "Already up to date. No changes to pull."
    exit 0
fi

log "New changes detected. Current: ${CURRENT_COMMIT:0:7}, Remote: ${REMOTE_COMMIT:0:7}"

# Pull latest code from deployment branch
log "Pulling latest code..."
sudo -u pi git pull origin deployment

# Update Python dependencies if requirements.txt changed
if sudo -u pi git diff --name-only "$CURRENT_COMMIT" "$REMOTE_COMMIT" | grep -q "requirements.txt"; then
    log "requirements.txt changed, updating dependencies..."
    sudo -u pi "$INSTALL_DIR/venv/bin/pip" install -r requirements.txt
else
    log "requirements.txt unchanged, skipping dependency update"
fi

# Restart the service
log "Restarting $SERVICE_NAME service..."
systemctl restart "$SERVICE_NAME"

# Wait a moment and check status
sleep 3
if systemctl is-active --quiet "$SERVICE_NAME"; then
    log "Service restarted successfully"
    NEW_COMMIT=$(sudo -u pi git rev-parse HEAD)
    log "Updated to commit: ${NEW_COMMIT:0:7}"
else
    log "WARNING: Service failed to start after update"
    systemctl status "$SERVICE_NAME" --no-pager | tee -a "$LOG_FILE"
    exit 1
fi

log "===== Update completed successfully ====="
exit 0
