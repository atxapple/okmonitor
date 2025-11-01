#!/bin/bash
#
# OK Monitor Uninstall Script
#
# This script removes all OK Monitor components from the system
# EXCEPT Tailscale (to maintain remote access).
#
# Usage:
#   sudo ./uninstall.sh [OPTIONS]
#
# Options:
#   --keep-packages    Keep system packages (python3, opencv, ffmpeg, etc.)
#   --yes             Skip confirmation prompts
#   --help            Show this help message
#

set -e  # Exit on error

# Color output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
INSTALL_DIR="/opt/okmonitor"
KEEP_PACKAGES=false
AUTO_YES=false

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

log_step() {
    echo -e "${BLUE}[STEP]${NC} $1"
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --keep-packages)
            KEEP_PACKAGES=true
            shift
            ;;
        --yes)
            AUTO_YES=true
            shift
            ;;
        --help)
            echo "OK Monitor Uninstall Script"
            echo ""
            echo "Usage: sudo $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --keep-packages    Keep system packages (python3, opencv, ffmpeg, etc.)"
            echo "  --yes              Skip confirmation prompts"
            echo "  --help             Show this help message"
            echo ""
            echo "What will be removed:"
            echo "  • OK Monitor application (/opt/okmonitor)"
            echo "  • OK Monitor systemd services"
            echo "  • Comitup WiFi hotspot system"
            echo "  • System packages (optional)"
            echo ""
            echo "What will be preserved:"
            echo "  • Tailscale (to maintain remote access)"
            echo ""
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
    log_error "Please run as root (use sudo)"
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
    log_warn "Could not detect non-root user"
    ACTUAL_USER="pi"  # Fallback
fi

echo ""
echo "=========================================="
echo "  OK Monitor Uninstall Script"
echo "=========================================="
echo ""
log_warn "This script will remove OK Monitor from your system"
echo ""
echo "What will be removed:"
echo "  ✗ OK Monitor application ($INSTALL_DIR)"
echo "  ✗ OK Monitor systemd services"
echo "  ✗ Comitup WiFi hotspot system"
echo "  ✗ addwifi.sh script"
echo "  ✗ Update logs"
if [ "$KEEP_PACKAGES" = false ]; then
    echo "  ✗ System packages (python3, opencv, ffmpeg, etc.)"
fi
echo ""
echo "What will be preserved:"
echo "  ✓ Tailscale (remote access maintained)"
echo ""

if [ "$AUTO_YES" = false ]; then
    read -p "Are you sure you want to continue? (yes/no) " -r
    echo
    if [[ ! $REPLY =~ ^[Yy][Ee][Ss]$ ]]; then
        log_info "Uninstall cancelled"
        exit 0
    fi
fi

echo ""
log_info "Starting uninstall process..."
echo ""

# Track what was removed
REMOVED_ITEMS=()
FAILED_ITEMS=()

# Step 1: Stop and disable services
log_step "Step 1/7: Stopping and disabling OK Monitor services..."

SERVICES=("okmonitor-device.service" "okmonitor-update.service" "okmonitor-update.timer")
for service in "${SERVICES[@]}"; do
    if systemctl list-unit-files | grep -q "$service"; then
        log_info "Stopping $service..."
        systemctl stop "$service" 2>/dev/null || log_warn "Failed to stop $service (may not be running)"

        log_info "Disabling $service..."
        systemctl disable "$service" 2>/dev/null || log_warn "Failed to disable $service"

        REMOVED_ITEMS+=("Service: $service (stopped and disabled)")
    else
        log_warn "$service not found, skipping..."
    fi
done

# Step 2: Remove service files
log_step "Step 2/7: Removing service files..."

SERVICE_FILES=(
    "/etc/systemd/system/okmonitor-device.service"
    "/etc/systemd/system/okmonitor-update.service"
    "/etc/systemd/system/okmonitor-update.timer"
)

for service_file in "${SERVICE_FILES[@]}"; do
    if [ -f "$service_file" ]; then
        log_info "Removing $service_file..."
        rm -f "$service_file"
        REMOVED_ITEMS+=("File: $service_file")
    fi
done

# Reload systemd
log_info "Reloading systemd daemon..."
systemctl daemon-reload

# Step 3: Remove OK Monitor application directory
log_step "Step 3/7: Removing OK Monitor application..."

if [ -d "$INSTALL_DIR" ]; then
    log_info "Removing $INSTALL_DIR..."
    log_warn "This includes all code, configurations, captures, and logs"

    # Show directory size
    DIR_SIZE=$(du -sh "$INSTALL_DIR" 2>/dev/null | cut -f1 || echo "unknown")
    log_info "Directory size: $DIR_SIZE"

    rm -rf "$INSTALL_DIR"
    REMOVED_ITEMS+=("Directory: $INSTALL_DIR (including all data)")
else
    log_warn "$INSTALL_DIR not found, skipping..."
fi

# Step 4: Remove addwifi.sh from user home
log_step "Step 4/7: Removing addwifi.sh script..."

ADDWIFI_PATH="/home/$ACTUAL_USER/addwifi.sh"
if [ -f "$ADDWIFI_PATH" ]; then
    log_info "Removing $ADDWIFI_PATH..."
    rm -f "$ADDWIFI_PATH"
    REMOVED_ITEMS+=("File: $ADDWIFI_PATH")
else
    log_warn "$ADDWIFI_PATH not found, skipping..."
fi

# Step 5: Remove update logs
log_step "Step 5/7: Removing update logs..."

LOG_FILE="/var/log/okmonitor-update.log"
if [ -f "$LOG_FILE" ]; then
    log_info "Removing $LOG_FILE..."
    rm -f "$LOG_FILE"
    REMOVED_ITEMS+=("File: $LOG_FILE")
else
    log_warn "$LOG_FILE not found, skipping..."
fi

# Step 6: Uninstall Comitup
log_step "Step 6/7: Uninstalling Comitup WiFi hotspot..."

if systemctl list-unit-files | grep -q comitup.service; then
    log_info "Stopping comitup service..."
    systemctl stop comitup.service 2>/dev/null || true
    systemctl disable comitup.service 2>/dev/null || true
    REMOVED_ITEMS+=("Service: comitup.service (stopped and disabled)")
fi

# Remove comitup configuration
if [ -f "/etc/comitup.conf" ]; then
    log_info "Removing /etc/comitup.conf..."
    rm -f "/etc/comitup.conf"
    REMOVED_ITEMS+=("File: /etc/comitup.conf")
fi

# Remove comitup callback script
if [ -f "/usr/local/bin/comitup-callback.sh" ]; then
    log_info "Removing /usr/local/bin/comitup-callback.sh..."
    rm -f "/usr/local/bin/comitup-callback.sh"
    REMOVED_ITEMS+=("File: /usr/local/bin/comitup-callback.sh")
fi

# Uninstall comitup package
if dpkg -l | grep -q comitup; then
    log_info "Uninstalling comitup package..."
    apt-get remove -y comitup 2>/dev/null || log_warn "Failed to remove comitup package"
    REMOVED_ITEMS+=("Package: comitup")
fi

# Remove comitup repository
if [ -f "/etc/apt/sources.list.d/davesteele-comitup.list" ]; then
    log_info "Removing comitup APT repository..."
    rm -f "/etc/apt/sources.list.d/davesteele-comitup.list"
    apt-get update -qq 2>/dev/null || true
    REMOVED_ITEMS+=("Repository: davesteele-comitup")
fi

# Step 7: Remove system packages (optional)
log_step "Step 7/7: Handling system packages..."

if [ "$KEEP_PACKAGES" = true ]; then
    log_info "Keeping system packages (--keep-packages flag set)"
    log_info "The following packages will remain installed:"
    echo "  • python3, python3-pip, python3-venv"
    echo "  • git, v4l-utils"
    echo "  • opencv, ffmpeg, numpy libraries"
else
    log_warn "Removing system packages..."
    log_warn "Note: These packages may be used by other applications!"

    if [ "$AUTO_YES" = false ]; then
        read -p "Remove system packages? (yes/no) " -r
        echo
        if [[ ! $REPLY =~ ^[Yy][Ee][Ss]$ ]]; then
            log_info "Keeping system packages"
        else
            log_info "Removing packages..."
            PACKAGES_TO_REMOVE=(
                "python3-opencv"
                "libopencv-dev"
                "libopenblas-dev"
                "liblapack-dev"
                "gfortran"
                "ffmpeg"
                "v4l-utils"
            )

            for package in "${PACKAGES_TO_REMOVE[@]}"; do
                if dpkg -l | grep -q "^ii.*$package"; then
                    apt-get remove -y "$package" 2>/dev/null && REMOVED_ITEMS+=("Package: $package") || FAILED_ITEMS+=("Package: $package")
                fi
            done

            log_info "Running apt autoremove..."
            apt-get autoremove -y 2>/dev/null || true
        fi
    fi
fi

# Optional: Remove user from video group
log_info "Checking video group membership..."
if groups "$ACTUAL_USER" | grep -q video; then
    log_warn "User $ACTUAL_USER is in video group (needed for camera access)"

    if [ "$AUTO_YES" = false ]; then
        read -p "Remove $ACTUAL_USER from video group? (yes/no) " -r
        echo
        if [[ $REPLY =~ ^[Yy][Ee][Ss]$ ]]; then
            gpasswd -d "$ACTUAL_USER" video
            REMOVED_ITEMS+=("User $ACTUAL_USER removed from video group")
        fi
    fi
fi

echo ""
echo "=========================================="
echo "  Uninstall Complete"
echo "=========================================="
echo ""

# Summary
log_info "Summary of removed items:"
if [ ${#REMOVED_ITEMS[@]} -eq 0 ]; then
    echo "  • No items were removed (already clean)"
else
    for item in "${REMOVED_ITEMS[@]}"; do
        echo "  ✓ $item"
    done
fi

if [ ${#FAILED_ITEMS[@]} -gt 0 ]; then
    echo ""
    log_warn "Failed to remove:"
    for item in "${FAILED_ITEMS[@]}"; do
        echo "  ✗ $item"
    done
fi

echo ""
log_info "What was preserved:"
echo "  ✓ Tailscale - Remote access maintained"
if systemctl is-active --quiet tailscaled 2>/dev/null; then
    TAILSCALE_IP=$(tailscale ip -4 2>/dev/null || echo "unknown")
    echo "     Status: Active ($TAILSCALE_IP)"
fi

echo ""
log_info "To reinstall OK Monitor, run:"
echo "  sudo ./deployment/install_device.sh"
echo ""
log_info "Uninstall completed successfully!"
echo ""
