#!/bin/bash
# OK Monitor - Prepare Device for Cloning
# Run this script before creating a golden image

set -e

INSTALL_DIR="/opt/okmonitor"
ENV_FILE="$INSTALL_DIR/.env.device"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo -e "${RED}ERROR: Please run as root (use sudo)${NC}"
    exit 1
fi

echo -e "${BLUE}===== Prepare OK Monitor Device for Cloning =====${NC}"
echo ""
echo "This script will prepare this device to become a golden image."
echo ""
echo -e "${YELLOW}WARNING: This will:${NC}"
echo "  - Stop all OK Monitor services"
echo "  - Reset device ID to PLACEHOLDER"
echo "  - Clear all captured data and cached configurations"
echo "  - Logout from Tailscale"
echo "  - Clear system logs and shell history"
echo ""
read -p "Continue? (y/n) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Cancelled"
    exit 0
fi

echo ""
echo -e "${GREEN}Step 1: Stopping Services${NC}"
if systemctl is-active --quiet okmonitor-device; then
    systemctl stop okmonitor-device
    echo "  ✓ Stopped okmonitor-device"
else
    echo "  ℹ okmonitor-device not running"
fi

echo ""
echo -e "${GREEN}Step 2: Resetting Configuration${NC}"

if [ -f "$ENV_FILE" ]; then
    # Backup current config
    cp "$ENV_FILE" "$ENV_FILE.pre-clone-backup"
    echo "  ✓ Backed up configuration"

    # Reset device ID to placeholder
    sed -i 's/^DEVICE_ID=.*/DEVICE_ID=PLACEHOLDER_DEVICE_ID/' "$ENV_FILE"
    echo "  ✓ Reset device ID to PLACEHOLDER_DEVICE_ID"

    # Show current config
    echo ""
    echo "  Golden image will have this configuration:"
    grep -E "^(API_URL|DEVICE_ID|CAMERA_SOURCE)=" "$ENV_FILE" | sed 's/^/    /'
else
    echo -e "  ${YELLOW}⚠ No .env.device file found${NC}"
fi

echo ""
echo -e "${GREEN}Step 3: Clearing Data${NC}"

# Clear debug captures
if [ -d "$INSTALL_DIR/debug_captures" ]; then
    rm -rf "$INSTALL_DIR/debug_captures"/*
    echo "  ✓ Cleared debug captures"
fi

# Clear cached configurations
if [ -d "$INSTALL_DIR/config" ]; then
    rm -rf "$INSTALL_DIR/config"/*
    echo "  ✓ Cleared cached configurations"
fi

# Clear similarity cache if exists
if [ -f "$INSTALL_DIR/config/similarity_cache.json" ]; then
    rm -f "$INSTALL_DIR/config/similarity_cache.json"
    echo "  ✓ Cleared similarity cache"
fi

echo ""
echo -e "${GREEN}Step 4: Resetting Tailscale${NC}"
if command -v tailscale &> /dev/null; then
    if tailscale status &> /dev/null 2>&1; then
        tailscale logout 2>/dev/null || true
        echo "  ✓ Logged out from Tailscale"
    else
        echo "  ℹ Tailscale not connected"
    fi
else
    echo "  ℹ Tailscale not installed"
fi

echo ""
echo -e "${GREEN}Step 5: Clearing Logs${NC}"
journalctl --rotate
journalctl --vacuum-time=1s
echo "  ✓ Cleared system logs"

echo ""
echo -e "${GREEN}Step 6: Clearing History${NC}"

# Get the actual user (not root)
if [ -n "$SUDO_USER" ]; then
    ACTUAL_USER="$SUDO_USER"
    USER_HOME=$(eval echo ~$SUDO_USER)
else
    ACTUAL_USER=$(getent passwd | awk -F: '$3 >= 1000 && $3 < 65534 && $6 ~ /^\/home\// {print $1; exit}')
    USER_HOME=$(eval echo ~$ACTUAL_USER)
fi

if [ -n "$ACTUAL_USER" ] && [ -d "$USER_HOME" ]; then
    # Clear bash history
    if [ -f "$USER_HOME/.bash_history" ]; then
        cat /dev/null > "$USER_HOME/.bash_history"
        chown "$ACTUAL_USER:$ACTUAL_USER" "$USER_HOME/.bash_history"
        echo "  ✓ Cleared bash history for $ACTUAL_USER"
    fi
fi

# Clear root history too
if [ -f "/root/.bash_history" ]; then
    cat /dev/null > /root/.bash_history
    echo "  ✓ Cleared root bash history"
fi

echo ""
echo -e "${GREEN}===== Device Ready for Cloning! =====${NC}"
echo ""
echo -e "${BLUE}What happens next:${NC}"
echo ""
echo "  1. Shutdown this device:"
echo "     sudo shutdown -h now"
echo ""
echo "  2. Remove SD card and create image on your computer:"
echo ""
echo "     ${YELLOW}Windows:${NC}"
echo "       Use Win32 Disk Imager to read SD card to .img file"
echo ""
echo "     ${YELLOW}macOS:${NC}"
echo "       diskutil list"
echo "       diskutil unmountDisk /dev/diskN"
echo "       sudo dd if=/dev/rdiskN of=okmonitor-golden.img bs=4m status=progress"
echo ""
echo "     ${YELLOW}Linux:${NC}"
echo "       lsblk"
echo "       sudo dd if=/dev/sdX of=okmonitor-golden.img bs=4M status=progress"
echo ""
echo "  3. (Optional) Shrink image to save space:"
echo "     wget https://raw.githubusercontent.com/Drewsif/PiShrink/master/pishrink.sh"
echo "     chmod +x pishrink.sh"
echo "     sudo ./pishrink.sh okmonitor-golden.img"
echo ""
echo "  4. Clone this image to new SD cards"
echo ""
echo "  5. On each cloned device, run:"
echo "     sudo deployment/customize_clone.sh"
echo ""
echo -e "${GREEN}Golden image configuration saved as:${NC}"
echo "  $ENV_FILE.pre-clone-backup"
echo ""
echo -e "${YELLOW}Ready to shutdown!${NC}"
echo ""
