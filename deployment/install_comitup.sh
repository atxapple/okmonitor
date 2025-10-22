#!/bin/bash
#
# Comitup Installation Script for OK Monitor
#
# This script installs and configures Comitup for easy WiFi setup
# on Raspberry Pi devices without keyboard/monitor access.
#
# Usage:
#   sudo ./install_comitup.sh
#

set -e  # Exit on error

# Color output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Logging functions
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    log_error "Please run as root (use sudo)"
    exit 1
fi

# Check if running on Raspberry Pi
if ! grep -q "Raspberry Pi" /proc/cpuinfo 2>/dev/null; then
    log_warn "This script is designed for Raspberry Pi. Proceed with caution."
fi

log_info "Starting Comitup installation..."

# Step 1: Download Comitup repository package
log_info "Step 1/5: Downloading Comitup repository package..."
cd /tmp
wget -q --show-progress https://davesteele.github.io/comitup/deb/davesteele-comitup-apt-source_1.3_all.deb

if [ ! -f "davesteele-comitup-apt-source_1.3_all.deb" ]; then
    log_error "Failed to download Comitup repository package"
    exit 1
fi

# Step 2: Install repository package
log_info "Step 2/5: Installing Comitup repository..."
dpkg -i davesteele-comitup-apt-source*.deb || {
    log_error "Failed to install repository package"
    exit 1
}

# Step 3: Update package list
log_info "Step 3/5: Updating package list..."
apt-get update || {
    log_error "Failed to update package list"
    exit 1
}

# Step 4: Install Comitup
log_info "Step 4/5: Installing Comitup..."
apt-get install -y comitup || {
    log_error "Failed to install Comitup"
    exit 1
}

# Step 5: Configure Comitup for OK Monitor
log_info "Step 5/5: Configuring Comitup..."

# Create configuration file
cat > /etc/comitup.conf <<EOF
# Comitup Configuration for OK Monitor
# https://davesteele.github.io/comitup/

# Access Point name when no WiFi is configured
# Format: okmonitor-NNNN where NNNN is based on device ID
ap_name: okmonitor

# Access Point password
# Leave empty for open/passwordless access point
ap_password:

# Web service port for WiFi configuration
web_service: 80

# Enable external callback when connection state changes
# This can be used to restart OK Monitor service after WiFi connects
external_callback: /usr/local/bin/comitup-callback.sh

# Verbose logging for troubleshooting
verbose: false
EOF

log_info "Created Comitup configuration at /etc/comitup.conf"

# Create callback script to restart OK Monitor after WiFi connects
cat > /usr/local/bin/comitup-callback.sh <<'EOF'
#!/bin/bash
# Comitup callback for OK Monitor
# Called when WiFi connection state changes

STATE=$1  # HOTSPOT, CONNECTING, CONNECTED, FAILED

case "$STATE" in
    CONNECTED)
        # WiFi connected - restart OK Monitor to ensure it uses new network
        logger -t comitup-callback "WiFi connected, restarting OK Monitor service"
        systemctl restart okmonitor-device.service 2>/dev/null || true
        ;;
    HOTSPOT)
        logger -t comitup-callback "No WiFi configured, running in hotspot mode"
        ;;
    CONNECTING)
        logger -t comitup-callback "Connecting to WiFi..."
        ;;
    FAILED)
        logger -t comitup-callback "WiFi connection failed, reverting to hotspot"
        ;;
esac
EOF

chmod +x /usr/local/bin/comitup-callback.sh
log_info "Created callback script at /usr/local/bin/comitup-callback.sh"

# Enable and start Comitup service
log_info "Enabling Comitup service..."
systemctl enable comitup.service
systemctl start comitup.service

# Check service status
if systemctl is-active --quiet comitup.service; then
    log_info "✓ Comitup service is running"
else
    log_warn "Comitup service may not be running properly. Check: systemctl status comitup"
fi

# Clean up
rm -f /tmp/davesteele-comitup-apt-source*.deb

log_info ""
log_info "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
log_info "✓ Comitup installation complete!"
log_info "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
log_info ""
log_info "Configuration:"
log_info "  • Hotspot SSID: okmonitor-XXXX (auto-generated)"
log_info "  • Hotspot Password: NONE (open network)"
log_info "  • Web Interface: http://10.41.0.1 (when in hotspot mode)"
log_info ""
log_info "Usage:"
log_info "  1. Reboot the Raspberry Pi"
log_info "  2. Connect to 'okmonitor-XXXX' WiFi network (no password)"
log_info "  3. Open browser to http://10.41.0.1"
log_info "  4. Select and configure your WiFi network"
log_info ""
log_info "Commands:"
log_info "  • Check status: systemctl status comitup"
log_info "  • View logs: journalctl -u comitup -f"
log_info "  • Edit config: sudo nano /etc/comitup.conf"
log_info "  • List networks: comitup-cli"
log_info ""
log_info "For more information:"
log_info "  • Documentation: https://davesteele.github.io/comitup/"
log_info "  • OK Monitor: See deployment/COMITUP.md"
log_info ""
