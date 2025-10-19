#!/bin/bash
# Tailscale Installation Script for OK Monitor Fleet
# Enables secure remote SSH/VNC access to Raspberry Pi devices

set -e

OKMONITOR_DIR="/opt/okmonitor"
ENV_FILE="$OKMONITOR_DIR/.env.device"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo -e "${RED}ERROR: Please run as root (use sudo)${NC}"
    exit 1
fi

echo "===== Tailscale Installation for OK Monitor ====="
echo ""

# Parse command line arguments
AUTH_KEY=""
HOSTNAME_PREFIX="okmonitor"

while [[ $# -gt 0 ]]; do
    case $1 in
        --auth-key)
            AUTH_KEY="$2"
            shift 2
            ;;
        --hostname-prefix)
            HOSTNAME_PREFIX="$2"
            shift 2
            ;;
        --help)
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --auth-key KEY          Tailscale auth key for non-interactive setup"
            echo "  --hostname-prefix NAME  Hostname prefix (default: okmonitor)"
            echo "  --help                  Show this help message"
            echo ""
            echo "The script will read DEVICE_ID from $ENV_FILE"
            echo "and set hostname as: {prefix}-{DEVICE_ID}"
            echo ""
            echo "Example:"
            echo "  sudo $0 --auth-key tskey-auth-xxxxx"
            exit 0
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
done

# Try to read DEVICE_ID from .env.device
DEVICE_ID=""
if [ -f "$ENV_FILE" ]; then
    # Extract DEVICE_ID from env file
    DEVICE_ID=$(grep "^DEVICE_ID=" "$ENV_FILE" | cut -d'=' -f2 | tr -d ' "' || true)
fi

# Prompt for device ID if not found
if [ -z "$DEVICE_ID" ]; then
    echo -e "${YELLOW}Device ID not found in $ENV_FILE${NC}"
    read -p "Enter device ID (e.g., okmonitor1, floor-01-cam): " DEVICE_ID
    if [ -z "$DEVICE_ID" ]; then
        echo -e "${RED}ERROR: Device ID is required${NC}"
        exit 1
    fi
fi

# Construct hostname
TAILSCALE_HOSTNAME="${HOSTNAME_PREFIX}-${DEVICE_ID}"

echo -e "${GREEN}Configuration:${NC}"
echo "  Device ID: $DEVICE_ID"
echo "  Tailscale Hostname: $TAILSCALE_HOSTNAME"
echo ""

# Prompt for auth key if not provided
if [ -z "$AUTH_KEY" ]; then
    echo -e "${YELLOW}No auth key provided.${NC}"
    echo "You can generate an auth key at: https://login.tailscale.com/admin/settings/keys"
    echo ""
    read -p "Enter Tailscale auth key (or press Enter for interactive auth): " AUTH_KEY
fi

read -p "Continue with installation? (y/n) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Installation cancelled"
    exit 0
fi

echo ""
echo "Step 1: Installing Tailscale..."

# Add Tailscale's GPG key and repository
if [ ! -f /usr/share/keyrings/tailscale-archive-keyring.gpg ]; then
    curl -fsSL https://pkgs.tailscale.com/stable/raspbian/bookworm.noarmor.gpg | \
        tee /usr/share/keyrings/tailscale-archive-keyring.gpg >/dev/null
fi

if [ ! -f /etc/apt/sources.list.d/tailscale.list ]; then
    curl -fsSL https://pkgs.tailscale.com/stable/raspbian/bookworm.tailscale-keyring.list | \
        tee /etc/apt/sources.list.d/tailscale.list
fi

apt-get update -qq
apt-get install -y tailscale

echo -e "${GREEN}✓ Tailscale installed${NC}"

echo ""
echo "Step 2: Configuring Tailscale..."

# Enable IP forwarding (useful for subnet routing)
if ! grep -q "net.ipv4.ip_forward=1" /etc/sysctl.conf; then
    echo "net.ipv4.ip_forward=1" >> /etc/sysctl.conf
    sysctl -p /etc/sysctl.conf
fi

echo -e "${GREEN}✓ IP forwarding enabled${NC}"

echo ""
echo "Step 3: Connecting to Tailscale..."

# Start Tailscale
if [ -n "$AUTH_KEY" ]; then
    echo "Using auth key for non-interactive setup..."
    tailscale up --authkey="$AUTH_KEY" --hostname="$TAILSCALE_HOSTNAME" --accept-routes
else
    echo "Starting interactive authentication..."
    echo "A URL will be displayed - open it in your browser to authenticate."
    tailscale up --hostname="$TAILSCALE_HOSTNAME" --accept-routes
fi

# Wait a moment for connection
sleep 3

# Check status
if tailscale status | grep -q "$TAILSCALE_HOSTNAME"; then
    echo -e "${GREEN}✓ Connected to Tailscale!${NC}"
else
    echo -e "${YELLOW}Warning: Could not verify connection. Check with: tailscale status${NC}"
fi

echo ""
echo "Step 4: Verifying SSH access..."

# Check if SSH is enabled
if systemctl is-enabled ssh >/dev/null 2>&1 || systemctl is-enabled sshd >/dev/null 2>&1; then
    echo -e "${GREEN}✓ SSH service is enabled${NC}"
else
    echo -e "${YELLOW}Warning: SSH service not found or not enabled${NC}"
    read -p "Enable SSH now? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        systemctl enable ssh
        systemctl start ssh
        echo -e "${GREEN}✓ SSH enabled${NC}"
    fi
fi

# Get Tailscale IP
TAILSCALE_IP=$(tailscale ip -4 2>/dev/null || echo "unknown")

echo ""
echo "===== Installation Complete! ====="
echo ""
echo -e "${GREEN}Your device is now accessible via Tailscale:${NC}"
echo ""
echo "  Hostname: $TAILSCALE_HOSTNAME"
echo "  Tailscale IP: $TAILSCALE_IP"
echo ""
echo -e "${GREEN}Access via SSH:${NC}"
echo "  ssh $(whoami)@$TAILSCALE_HOSTNAME"
echo "  ssh $(whoami)@$TAILSCALE_IP"
echo ""
echo -e "${GREEN}Access via VNC (if enabled):${NC}"
echo "  Connect to: $TAILSCALE_HOSTNAME:5900"
echo "  Or: $TAILSCALE_IP:5900"
echo ""
echo -e "${YELLOW}Next steps:${NC}"
echo "  1. Install Tailscale on your laptop/desktop"
echo "  2. Check device status: tailscale status"
echo "  3. View all devices: https://login.tailscale.com/admin/machines"
echo "  4. Configure ACLs if needed: https://login.tailscale.com/admin/acls"
echo ""
echo -e "${GREEN}Useful commands:${NC}"
echo "  tailscale status        - Show connection status"
echo "  tailscale ip            - Show Tailscale IPs"
echo "  tailscale up            - Reconnect"
echo "  tailscale down          - Disconnect"
echo "  sudo tailscale logout   - Remove device from Tailnet"
echo ""
