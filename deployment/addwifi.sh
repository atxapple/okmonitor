#!/bin/bash
# WiFi Network Configuration Script for OK Monitor
# Adds or updates WiFi network profiles using NetworkManager

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Show help
show_help() {
    cat << EOF
Usage: $0 SSID PASSWORD [PRIORITY] [--hidden]

Add or update a WiFi network profile with persistent configuration.

Arguments:
  SSID        Network name (required)
  PASSWORD    WiFi password (required)
  PRIORITY    Connection priority 0-999 (default: 100, higher = preferred)
  --hidden    Flag for hidden networks (optional)

Options:
  --help      Show this help message
  --list      List all saved WiFi profiles

Examples:
  # Add a basic network
  $0 "MyNetwork" "mypassword123"

  # Add with custom priority (higher priority connects first)
  $0 "WorkNetwork" "workpass" 200

  # Add hidden network
  $0 "HiddenNetwork" "secretpass" 100 --hidden

  # List all saved networks
  $0 --list

Priority Tips:
  - Home network: 100 (default)
  - Work network: 150
  - Mobile hotspot: 50
  - Higher numbers connect first when multiple networks available

EOF
    exit 0
}

# List saved WiFi profiles
list_profiles() {
    echo -e "${BLUE}===== Saved WiFi Profiles =====${NC}"
    echo ""

    # Get all WiFi connections with their priority
    nmcli -t -f NAME,TYPE,AUTOCONNECT,AUTOCONNECT-PRIORITY connection show | \
    awk -F: '$2=="802-11-wireless" {
        name=$1
        auto=$3
        prio=$4
        if (prio == "") prio="0"
        printf "%-30s  Priority: %-4s  Auto-connect: %s\n", name, prio, auto
    }' | sort -t: -k2 -rn

    echo ""
    echo -e "${GREEN}Active connection:${NC}"
    nmcli -t -f NAME,TYPE,DEVICE connection show --active | \
    awk -F: '$2=="802-11-wireless" {printf "  %s (on %s)\n", $1, $3}'

    echo ""
    exit 0
}

# Handle options
if [ $# -eq 0 ]; then
    echo -e "${RED}ERROR: No arguments provided${NC}"
    echo "Use --help for usage information"
    exit 1
fi

if [ "$1" = "--help" ] || [ "$1" = "-h" ]; then
    show_help
fi

if [ "$1" = "--list" ] || [ "$1" = "-l" ]; then
    list_profiles
fi

# Parse arguments
SSID="${1:-}"
PASSWORD="${2:-}"
PRIORITY="${3:-100}"
HIDDEN_FLAG="${4:-}"

# Validate required arguments
if [ -z "$SSID" ]; then
    echo -e "${RED}ERROR: SSID is required${NC}"
    echo "Use --help for usage information"
    exit 1
fi

if [ -z "$PASSWORD" ]; then
    echo -e "${RED}ERROR: Password is required${NC}"
    echo "Use --help for usage information"
    exit 1
fi

# Validate priority is a number
if ! [[ "$PRIORITY" =~ ^[0-9]+$ ]]; then
    echo -e "${RED}ERROR: Priority must be a number (0-999)${NC}"
    exit 1
fi

echo -e "${BLUE}===== WiFi Configuration =====${NC}"
echo ""
echo -e "${GREEN}Network:${NC}  $SSID"
echo -e "${GREEN}Priority:${NC} $PRIORITY"
if [ "$HIDDEN_FLAG" = "--hidden" ]; then
    echo -e "${GREEN}Hidden:${NC}   Yes"
fi
echo ""

# Auto-detect WiFi interface
IFACE="$(nmcli -t -f DEVICE,TYPE device status | awk -F: '$2=="wifi"{print $1; exit}')"

if [ -z "$IFACE" ]; then
    echo -e "${RED}ERROR: No WiFi interface found${NC}"
    echo "Available interfaces:"
    nmcli device status
    exit 1
fi

echo -e "${GREEN}WiFi interface:${NC} $IFACE"
echo ""

# Connection name (same as SSID for simplicity)
CON_NAME="$SSID"

# Create or update profile
if nmcli -t -f NAME connection show | grep -Fxq "$CON_NAME"; then
    echo -e "${YELLOW}Profile '$CON_NAME' exists — updating…${NC}"
else
    echo -e "${GREEN}Creating new profile '$CON_NAME'…${NC}"
    if [ "$HIDDEN_FLAG" = "--hidden" ]; then
        nmcli connection add type wifi ifname "$IFACE" con-name "$CON_NAME" ssid "$SSID" \
            802-11-wireless.hidden yes
    else
        nmcli connection add type wifi ifname "$IFACE" con-name "$CON_NAME" ssid "$SSID"
    fi
fi

# Configure WPA2-PSK security
echo -e "${GREEN}Configuring security…${NC}"
nmcli connection modify "$CON_NAME" \
    wifi-sec.key-mgmt wpa-psk \
    wifi-sec.psk "$PASSWORD"

# Set autoconnect and priority
echo -e "${GREEN}Setting priority and autoconnect…${NC}"
nmcli connection modify "$CON_NAME" \
    connection.autoconnect yes \
    connection.autoconnect-priority "$PRIORITY"

# Use stable MAC address
nmcli connection modify "$CON_NAME" \
    802-11-wireless.cloned-mac-address stable

# Set retry policy
nmcli connection modify "$CON_NAME" \
    connection.autoconnect-retries 0

echo -e "${GREEN}Activating connection…${NC}"
if nmcli connection up "$CON_NAME" ifname "$IFACE" 2>/dev/null; then
    echo ""
    echo -e "${GREEN}===== Success! =====${NC}"
    echo -e "${GREEN}Connected to:${NC} $SSID"
    echo ""

    # Show connection info
    IP_ADDR=$(nmcli -t -f IP4.ADDRESS device show "$IFACE" | cut -d: -f2 | head -1)
    if [ -n "$IP_ADDR" ]; then
        echo -e "${GREEN}IP Address:${NC} $IP_ADDR"
    fi

    GATEWAY=$(nmcli -t -f IP4.GATEWAY device show "$IFACE" | cut -d: -f2)
    if [ -n "$GATEWAY" ]; then
        echo -e "${GREEN}Gateway:${NC}    $GATEWAY"
    fi

    echo ""
    echo -e "${BLUE}The network will automatically connect on boot.${NC}"
else
    echo ""
    echo -e "${YELLOW}===== Profile Saved (Connection Failed) =====${NC}"
    echo -e "${YELLOW}The profile has been saved but could not connect now.${NC}"
    echo -e "${YELLOW}This may be normal if:${NC}"
    echo "  - Network is out of range"
    echo "  - Password is incorrect"
    echo "  - Network is not available yet"
    echo ""
    echo -e "${BLUE}The device will auto-connect when the network is available.${NC}"
fi

echo ""
echo -e "${BLUE}Use '$0 --list' to see all saved networks.${NC}"
echo ""
