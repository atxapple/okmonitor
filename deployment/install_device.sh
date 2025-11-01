#!/bin/bash
# OK Monitor Device Installation Script for Raspberry Pi 5
# Run this script on a fresh Raspberry Pi OS (Bookworm) installation

set -e

INSTALL_DIR="/opt/okmonitor"
REPO_URL="https://github.com/atxapple/okmonitor.git"
BRANCH="main"
TAILSCALE_KEY=""
SKIP_TAILSCALE=false
INSTALL_TAILSCALE=false

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --tailscale-key)
            TAILSCALE_KEY="$2"
            shift 2
            ;;
        --skip-tailscale)
            SKIP_TAILSCALE=true
            shift
            ;;
        --install-tailscale)
            INSTALL_TAILSCALE=true
            shift
            ;;
        --help)
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --tailscale-key KEY    Tailscale auth key for automatic remote access setup"
            echo "  --skip-tailscale       Skip Tailscale installation/configuration (safe for reinstalls)"
            echo "  --install-tailscale    Force Tailscale installation/reconfiguration"
            echo "  --help                 Show this help message"
            echo ""
            echo "Examples:"
            echo "  sudo $0                                    # Fresh install with Tailscale"
            echo "  sudo $0 --tailscale-key tskey-auth-xxxxx  # Fresh install with auto-connect"
            echo "  sudo $0 --skip-tailscale                  # Reinstall, keep existing Tailscale"
            echo "  sudo $0 --install-tailscale               # Reinstall and reconfigure Tailscale"
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

# Check if .env.device exists when Tailscale key is provided
if [ -n "$TAILSCALE_KEY" ] && [ ! -f "/opt/okmonitor/.env.device" ]; then
    echo "===== IMPORTANT: Configuration Required ====="
    echo ""
    echo "ERROR: You provided a Tailscale key, but /opt/okmonitor/.env.device doesn't exist yet."
    echo ""
    echo "The DEVICE_ID from .env.device is used to set the Tailscale hostname."
    echo ""
    echo "Please create the configuration file first:"
    echo "  1. sudo mkdir -p /opt/okmonitor"
    echo "  2. sudo nano /opt/okmonitor/.env.device"
    echo "  3. Add at minimum:"
    echo "     API_URL=https://your-api-url.com"
    echo "     DEVICE_ID=your-device-id"
    echo "     CAMERA_SOURCE=0"
    echo "  4. Re-run this installer with --tailscale-key"
    echo ""
    echo "Or run installer without --tailscale-key and connect to Tailscale later."
    echo ""
    exit 1
fi

echo "===== OK Monitor Device Installation ====="
echo "Installing for user: $USER_NAME"
echo ""
echo "This script will:"
echo "  1. Install system dependencies"
echo "  2. Clone the repository to $INSTALL_DIR"
echo "  3. Set up Python virtual environment"
echo "  4. Configure systemd services"
echo "  5. Enable auto-start and auto-update"
echo "  6. Install Comitup (WiFi hotspot for easy setup)"
echo "  7. Install addwifi.sh (backup WiFi configuration tool)"
echo "  8. Install Tailscale for remote access"
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

    # Backup .env.device if it exists and contains user configuration
    if [ -f "$INSTALL_DIR/.env.device" ]; then
        echo "Found existing .env.device configuration - backing up..."
        cp "$INSTALL_DIR/.env.device" "/tmp/.env.device.backup"
        echo "✓ Configuration backed up to /tmp/.env.device.backup"
    fi

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

    # Restore .env.device backup if it exists
    if [ -f "/tmp/.env.device.backup" ]; then
        echo "Restoring your .env.device configuration..."
        cp "/tmp/.env.device.backup" "$INSTALL_DIR/.env.device"
        chown "$USER_NAME:$USER_NAME" "$INSTALL_DIR/.env.device"
        rm -f "/tmp/.env.device.backup"
        echo "✓ Configuration restored successfully"
    fi
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
echo "Step 7: Installing Comitup (WiFi hotspot)..."
if [ -f "deployment/install_comitup.sh" ]; then
    chmod +x deployment/install_comitup.sh
    # Run Comitup installer in non-interactive mode
    echo "Installing Comitup for easy WiFi configuration..."
    cd deployment
    ./install_comitup.sh
    cd "$INSTALL_DIR"
    echo "✓ Comitup installed - device will create 'okmonitor-XXXX' hotspot when no WiFi configured"
else
    echo "WARNING: Comitup installer not found, skipping..."
fi

echo ""
echo "Step 8: Installing addwifi.sh (backup WiFi tool)..."
cp deployment/addwifi.sh "/home/$USER_NAME/addwifi.sh"
chmod +x "/home/$USER_NAME/addwifi.sh"
chown "$USER_NAME:$USER_NAME" "/home/$USER_NAME/addwifi.sh"
echo "✓ WiFi script installed to: /home/$USER_NAME/addwifi.sh"

# Function to check Tailscale status
check_tailscale_status() {
    # Check if tailscale command exists
    if ! command -v tailscale &> /dev/null; then
        echo "not-installed"
        return
    fi

    # Check if tailscaled is running
    if ! systemctl is-active --quiet tailscaled 2>/dev/null; then
        echo "installed"
        return
    fi

    # Check if connected by looking for an IP address
    local ts_ip=$(tailscale ip -4 2>/dev/null)
    if [ -n "$ts_ip" ] && [ "$ts_ip" != "100.64.0.0" ]; then
        echo "connected"
        return
    fi

    echo "installed"
}

# Function to show current Tailscale info
show_tailscale_info() {
    local ts_ip=$(tailscale ip -4 2>/dev/null || echo "unknown")
    local ts_hostname=$(tailscale status --json 2>/dev/null | grep -o '"HostName":"[^"]*"' | cut -d'"' -f4 || echo "unknown")

    echo "  Current Tailscale IP: $ts_ip"
    echo "  Current Hostname: $ts_hostname"
    echo "  Status: Connected and active"
}

echo ""
echo "Step 9: Configuring Tailscale..."

# Check if user wants to skip Tailscale entirely
if [ "$SKIP_TAILSCALE" = true ]; then
    echo "✓ Skipping Tailscale (--skip-tailscale flag set)"
    echo "  Tailscale configuration unchanged"
else
    # Check current Tailscale status
    TS_STATUS=$(check_tailscale_status)

    # Decide what to do based on status and flags
    SHOULD_INSTALL=false

    if [ "$INSTALL_TAILSCALE" = true ] || [ -n "$TAILSCALE_KEY" ]; then
        # User explicitly wants to install/reconfigure
        SHOULD_INSTALL=true
        if [ "$TS_STATUS" = "connected" ]; then
            echo "WARNING: Tailscale is currently connected. Reconfiguration may disconnect you."
            show_tailscale_info
        fi
    elif [ "$TS_STATUS" = "connected" ]; then
        # Tailscale already connected - ask to keep
        echo "Tailscale is already connected:"
        show_tailscale_info
        echo ""
        read -p "Keep current Tailscale setup? (Y/n) " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Nn]$ ]]; then
            SHOULD_INSTALL=true
        else
            echo "✓ Keeping existing Tailscale configuration"
        fi
    elif [ "$TS_STATUS" = "installed" ]; then
        # Tailscale installed but not connected - ask to configure
        echo "Tailscale is installed but not connected."
        read -p "Configure Tailscale now? (y/N) " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            SHOULD_INSTALL=true
        else
            echo "✓ Skipping Tailscale configuration"
        fi
    else
        # Not installed - proceed with installation
        SHOULD_INSTALL=true
    fi

    # Install/configure Tailscale if needed
    if [ "$SHOULD_INSTALL" = true ]; then
        chmod +x deployment/install_tailscale.sh

        # If Tailscale not installed, install it first
        if [ "$TS_STATUS" = "not-installed" ]; then
            echo "Installing Tailscale..."
            deployment/install_tailscale.sh --install-only
        fi

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
            if [ "$TS_STATUS" = "not-installed" ]; then
                echo "✓ Tailscale installed (not connected)"
                echo "  To connect later: sudo deployment/install_tailscale.sh --auth-key YOUR_KEY"
            else
                echo "✓ Tailscale ready (use: sudo tailscale up)"
            fi
        fi
    fi
fi

echo ""
echo "===== Installation Complete ====="
echo ""
echo "✓ Comitup installed - WiFi hotspot will be available on boot"
echo "✓ addwifi.sh installed - backup WiFi configuration tool"
echo "✓ Tailscale installed - remote access ready"
echo ""
echo "Next steps:"
echo "  1. IMPORTANT: Edit configuration: sudo nano $INSTALL_DIR/.env.device"
echo "     - Update API_URL with your Railway/cloud URL"
echo "     - Set DEVICE_ID to a unique identifier"
echo ""
echo "Configure WiFi - Choose one method:"
echo ""
echo "  Method 1: Comitup (Recommended - no SSH needed)"
echo "    1. Reboot device: sudo reboot"
echo "    2. Connect phone to 'okmonitor-XXXX' WiFi (no password)"
echo "    3. Open browser: http://10.41.0.1"
echo "    4. Select and configure customer WiFi"
echo "    📖 Full guide: deployment/COMITUP.md"
echo ""
echo "  Method 2: addwifi.sh (Backup - requires SSH)"
echo "    ~/addwifi.sh \"Network-Name\" \"password\" [priority]"
echo "    ~/addwifi.sh --list    # Show saved networks"
echo "    📖 Full guide: deployment/WIFI.md"
echo ""
if [ -z "$TAILSCALE_KEY" ]; then
    echo "Connect to Tailscale (for remote access):"
    echo "  NOTE: Configure .env.device FIRST (DEVICE_ID is used for hostname)"
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
