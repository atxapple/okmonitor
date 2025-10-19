#!/bin/bash
# OK Monitor Device Installation Script for Raspberry Pi 5
# Run this script on a fresh Raspberry Pi OS (Bookworm) installation

set -e

INSTALL_DIR="/opt/okmonitor"
REPO_URL="https://github.com/atxapple/okmonitor.git"
BRANCH="main"

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
echo "===== Installation Complete ====="
echo ""
echo "Next steps:"
echo "  1. Edit configuration: sudo nano $INSTALL_DIR/.env.device"
echo "  2. Update API_URL with your Railway/cloud URL"
echo "  3. Set DEVICE_ID to a unique identifier"
echo "  4. Update REPO_URL in this script if not done already"
echo ""
echo "Test the device program:"
echo "  sudo systemctl start okmonitor-device"
echo "  sudo journalctl -u okmonitor-device -f"
echo ""
echo "Check update timer:"
echo "  sudo systemctl list-timers okmonitor-update"
echo ""
echo "Manual update test:"
echo "  sudo $INSTALL_DIR/deployment/update_device.sh"
echo ""
echo "After confirming configuration is correct:"
echo "  sudo reboot"
echo ""
