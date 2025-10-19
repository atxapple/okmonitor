#!/bin/bash
# OK Monitor Clone Customization Script
# Run this after cloning the golden image to a new device

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

echo -e "${BLUE}===== OK Monitor Clone Customization =====${NC}"
echo ""
echo "This script will customize this cloned device with a unique identity."
echo ""

# Check if this looks like a cloned image
if [ -f "$ENV_FILE" ]; then
    CURRENT_ID=$(grep "^DEVICE_ID=" "$ENV_FILE" | cut -d'=' -f2 | tr -d ' "' || echo "")
    if [ "$CURRENT_ID" = "PLACEHOLDER_DEVICE_ID" ]; then
        echo -e "${YELLOW}Detected placeholder device ID. This appears to be a fresh clone.${NC}"
    elif [ -n "$CURRENT_ID" ]; then
        echo -e "${YELLOW}Current device ID: $CURRENT_ID${NC}"
        echo "This device may have been customized already."
        read -p "Continue with re-customization? (y/n) " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            echo "Customization cancelled"
            exit 0
        fi
    fi
else
    echo -e "${RED}ERROR: Environment file not found: $ENV_FILE${NC}"
    echo "This doesn't appear to be an OK Monitor device."
    exit 1
fi

echo ""
echo -e "${GREEN}Step 1: Set Device Identity${NC}"
echo ""
echo "Enter a unique DEVICE_ID for this device."
echo "Examples: okmonitor1, floor-01-cam, warehouse-entrance, lab-02"
echo ""

# Prompt for new device ID
read -p "New DEVICE_ID: " NEW_DEVICE_ID

# Validate device ID
if [ -z "$NEW_DEVICE_ID" ]; then
    echo -e "${RED}ERROR: Device ID cannot be empty${NC}"
    exit 1
fi

# Check for invalid characters
if [[ ! "$NEW_DEVICE_ID" =~ ^[a-zA-Z0-9_-]+$ ]]; then
    echo -e "${RED}ERROR: Device ID can only contain letters, numbers, hyphens, and underscores${NC}"
    exit 1
fi

echo ""
echo -e "${BLUE}New configuration:${NC}"
echo "  Device ID: $NEW_DEVICE_ID"
echo ""
read -p "Proceed with this configuration? (y/n) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Customization cancelled"
    exit 0
fi

echo ""
echo -e "${GREEN}Step 2: Updating Configuration${NC}"

# Backup original
cp "$ENV_FILE" "$ENV_FILE.backup.$(date +%Y%m%d_%H%M%S)"
echo "  ✓ Backed up original configuration"

# Update device ID in .env.device
sed -i "s/^DEVICE_ID=.*/DEVICE_ID=$NEW_DEVICE_ID/" "$ENV_FILE"
echo "  ✓ Updated device ID to: $NEW_DEVICE_ID"

echo ""
echo -e "${GREEN}Step 3: Clearing Clone-Specific Data${NC}"

# Stop services
if systemctl is-active --quiet okmonitor-device; then
    echo "  Stopping okmonitor-device service..."
    systemctl stop okmonitor-device
fi

# Clear any cached data from the golden image
if [ -d "$INSTALL_DIR/debug_captures" ]; then
    rm -rf "$INSTALL_DIR/debug_captures"/*
    echo "  ✓ Cleared debug captures"
fi

if [ -d "$INSTALL_DIR/config" ]; then
    rm -rf "$INSTALL_DIR/config"/*
    echo "  ✓ Cleared cached configurations"
fi

# Reset Tailscale if installed (each clone needs unique identity)
if command -v tailscale &> /dev/null; then
    if tailscale status &> /dev/null 2>&1; then
        echo "  Disconnecting Tailscale (will need to reconnect)..."
        tailscale logout 2>/dev/null || true
        echo "  ✓ Tailscale logged out"
        echo ""
        echo -e "${YELLOW}  Note: Reconnect Tailscale with:${NC}"
        echo "    sudo deployment/install_tailscale.sh --auth-key YOUR_KEY"
    fi
fi

echo ""
echo -e "${GREEN}Step 4: Restarting Services${NC}"

# Restart the device service
systemctl restart okmonitor-device
echo "  ✓ Restarted okmonitor-device service"

# Wait a moment for service to start
sleep 2

# Check service status
if systemctl is-active --quiet okmonitor-device; then
    echo -e "  ${GREEN}✓ Service is running${NC}"
else
    echo -e "  ${YELLOW}⚠ Service may have issues. Check logs:${NC}"
    echo "    sudo journalctl -u okmonitor-device -n 20"
fi

echo ""
echo -e "${GREEN}===== Customization Complete! =====${NC}"
echo ""
echo -e "${BLUE}Device Identity:${NC}"
echo "  Device ID: $NEW_DEVICE_ID"
echo ""
echo -e "${BLUE}Next Steps:${NC}"
echo ""

# Check if WiFi needs configuration
if ! nmcli -t -f DEVICE,STATE device | grep -q "wlan0:connected"; then
    echo "  1. Configure WiFi (if needed):"
    echo "     ~/addwifi.sh \"Network-Name\" \"password\""
    echo ""
fi

# Check if Tailscale needs setup
if command -v tailscale &> /dev/null; then
    if ! tailscale status &> /dev/null 2>&1; then
        echo "  2. Connect Tailscale for remote access:"
        echo "     sudo deployment/install_tailscale.sh --auth-key YOUR_KEY"
        echo ""
    fi
fi

echo "  3. Verify device is working:"
echo "     sudo systemctl status okmonitor-device"
echo "     sudo journalctl -u okmonitor-device -f"
echo ""

echo "  4. Check cloud connectivity:"
echo "     curl https://okmonitor-production.up.railway.app/health"
echo ""

echo -e "${GREEN}Device is ready for deployment!${NC}"
echo ""

# Show current configuration summary
echo -e "${BLUE}Current Configuration Summary:${NC}"
grep -E "^(API_URL|DEVICE_ID|CAMERA_SOURCE)=" "$ENV_FILE" | while read line; do
    echo "  $line"
done
echo ""
