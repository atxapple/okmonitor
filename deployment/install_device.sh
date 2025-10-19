#!/bin/bash
# OK Monitor Device Installation Script for Raspberry Pi 5
# Run this script on a fresh Raspberry Pi OS (Bookworm) installation

set -e

INSTALL_DIR="/opt/okmonitor"
REPO_URL="https://github.com/atxapple/okmonitor.git"
BRANCH="main"
TAILSCALE_KEY=""

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --tailscale-key)
            TAILSCALE_KEY="$2"
            shift 2
            ;;
        --help)
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --tailscale-key KEY    Tailscale auth key for automatic remote access setup"
            echo "  --help                 Show this help message"
            echo ""
            echo "Example:"
            echo "  sudo $0 --tailscale-key tskey-auth-xxxxx"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
done

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo "ERROR: Please run as root (use sudo)"
    exit 1
fi

# Detect the actual user who invoked sudo
if [ -n "$SUDO_USER" ]; then
    ACTUAL_USER="$SUDO_USER"
else
    # Fallback to first non-root user with home directory
    ACTUAL_USER=$(getent passwd | awk -F: '$3 >= 1000 && $3 < 65534 && $6 ~ /^\/home\// {print $1; exit}')
fi

if [ -z "$ACTUAL_USER" ]; then
    echo "ERROR: Could not detect non-root user. Please specify manually."
    echo "Run with: INSTALL_USER=your_username sudo -E $0"
    exit 1
fi

# Allow override via environment variable
USER_NAME="${INSTALL_USER:-$ACTUAL_USER}"

echo "===== OK Monitor Device Installation ====="
echo "Installing for user: $USER_NAME"
echo ""
echo "This script will:"
echo "  1. Install system dependencies"
echo "  2. Clone the repository to $INSTALL_DIR"
echo "  3. Set up Python virtual environment"
echo "  4. Configure systemd services"
echo "  5. Enable auto-start and auto-update"
echo "  6. Install WiFi management script"
echo "  7. Install Tailscale for remote access"
if [ -n "$TAILSCALE_KEY" ]; then
    echo "     → Will connect using provided auth key"
else
    echo "     → Will install but not connect (can connect later)"
fi
echo ""
read -p "Continue? (y/n) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Installation cancelled"
    exit 1
fi

echo ""
echo "Step 1: Installing system dependencies..."
apt-get update
apt-get install -y \
    python3 \
    python3-pip \
    python3-venv \
    git \
    v4l-utils \
    libopencv-dev \
    python3-opencv \
    libopenblas-dev \
    liblapack-dev \
    gfortran \
    ffmpeg

echo ""
echo "Step 2: Cloning repository..."
if [ -d "$INSTALL_DIR" ]; then
    echo "WARNING: $INSTALL_DIR already exists"
    read -p "Remove and re-clone? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        rm -rf "$INSTALL_DIR"
    else
        echo "Skipping clone step"
    fi
fi

if [ ! -d "$INSTALL_DIR" ]; then
    git clone --branch "$BRANCH" "$REPO_URL" "$INSTALL_DIR"
    chown -R "$USER_NAME:$USER_NAME" "$INSTALL_DIR"
fi

cd "$INSTALL_DIR"

echo ""
echo "Step 3: Setting up Python virtual environment..."
if [ ! -d "venv" ]; then
    sudo -u "$USER_NAME" python3 -m venv venv
fi

echo "Installing Python dependencies..."
sudo -u "$USER_NAME" venv/bin/pip install --upgrade pip
sudo -u "$USER_NAME" venv/bin/pip install -r requirements.txt

echo ""
echo "Step 4: Configuring environment..."
if [ ! -f ".env.device" ]; then
    cp deployment/.env.device.example .env.device
    echo "Created .env.device - PLEASE EDIT THIS FILE with your configuration!"
    echo "Edit: nano /opt/okmonitor/.env.device"
fi

# Create directories
echo "Creating directories..."
mkdir -p debug_captures
mkdir -p config
chown -R "$USER_NAME:$USER_NAME" debug_captures config

# Add user to video group for camera access
echo "Adding $USER_NAME user to video group..."
usermod -a -G video "$USER_NAME"

echo ""
echo "Step 5: Installing systemd services..."

# Copy and update service files with actual username
cp deployment/okmonitor-device.service /etc/systemd/system/
sed -i "s/User=pi/User=$USER_NAME/" /etc/systemd/system/okmonitor-device.service
sed -i "s/Group=pi/Group=$USER_NAME/" /etc/systemd/system/okmonitor-device.service

cp deployment/okmonitor-update.service /etc/systemd/system/
cp deployment/okmonitor-update.timer /etc/systemd/system/

# Make update script executable
chmod +x deployment/update_device.sh

# Reload systemd
systemctl daemon-reload

echo ""
echo "Step 6: Enabling services..."
systemctl enable okmonitor-device.service
systemctl enable okmonitor-update.timer

echo ""
echo "Step 7: Installing WiFi management script..."
cp deployment/addwifi.sh "/home/$USER_NAME/addwifi.sh"
chmod +x "/home/$USER_NAME/addwifi.sh"
chown "$USER_NAME:$USER_NAME" "/home/$USER_NAME/addwifi.sh"
echo "WiFi script installed to: /home/$USER_NAME/addwifi.sh"

echo ""
echo "Step 8: Installing Tailscale..."
# Install Tailscale software
chmod +x deployment/install_tailscale.sh
deployment/install_tailscale.sh --install-only

# If auth key provided, connect now
if [ -n "$TAILSCALE_KEY" ]; then
    echo "Connecting to Tailscale..."

    # Get device ID from env file if it exists
    DEVICE_ID=""
    if [ -f "$INSTALL_DIR/.env.device" ]; then
        DEVICE_ID=$(grep "^DEVICE_ID=" "$INSTALL_DIR/.env.device" | cut -d'=' -f2 | tr -d ' "' || echo "")
    fi

    # Use device ID for hostname if available, otherwise use generic name
    if [ -n "$DEVICE_ID" ] && [ "$DEVICE_ID" != "PLACEHOLDER_DEVICE_ID" ]; then
        HOSTNAME="okmonitor-${DEVICE_ID}"
    else
        HOSTNAME="okmonitor-$(hostname)"
    fi

    tailscale up --authkey="$TAILSCALE_KEY" --hostname="$HOSTNAME" --accept-routes

    # Get Tailscale IP
    sleep 2
    TAILSCALE_IP=$(tailscale ip -4 2>/dev/null || echo "unknown")
    echo "✓ Connected to Tailscale: $HOSTNAME ($TAILSCALE_IP)"
else
    echo "✓ Tailscale installed (not connected)"
    echo "  To connect later: sudo deployment/install_tailscale.sh --auth-key YOUR_KEY"
fi

echo ""
echo "===== Installation Complete ====="
echo ""
echo "Next steps:"
echo "  1. Edit configuration: sudo nano $INSTALL_DIR/.env.device"
echo "  2. Update API_URL with your Railway/cloud URL"
echo "  3. Set DEVICE_ID to a unique identifier"
echo ""
echo "Configure WiFi (if needed):"
echo "  ~/addwifi.sh \"Network-Name\" \"password\" [priority]"
echo "  ~/addwifi.sh --list    # Show saved networks"
echo "  ~/addwifi.sh --help    # Show full help"
echo ""
if [ -z "$TAILSCALE_KEY" ]; then
    echo "Connect to Tailscale (for remote access):"
    echo "  sudo deployment/install_tailscale.sh --auth-key YOUR_KEY"
    echo ""
fi
echo "Test the device program:"
echo "  sudo systemctl start okmonitor-device"
echo "  sudo journalctl -u okmonitor-device -f"
echo ""
echo "Verify deployment:"
echo "  sudo deployment/verify_deployment.sh"
echo ""
echo "Check update timer:"
echo "  sudo systemctl list-timers okmonitor-update"
echo ""
echo "After confirming configuration is correct:"
echo "  sudo reboot"
echo ""
