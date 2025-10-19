#!/bin/bash
# OK Monitor Deployment Verification Script
# Checks if device is properly configured and ready for production

set -e

INSTALL_DIR="/opt/okmonitor"
ENV_FILE="$INSTALL_DIR/.env.device"
SERVICE_NAME="okmonitor-device"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
BOLD='\033[1m'
NC='\033[0m' # No Color

# Counters
PASS_COUNT=0
FAIL_COUNT=0
WARN_COUNT=0
TOTAL_CHECKS=0

# Check results storage
declare -a CHECK_RESULTS

# Function to print check result
check_result() {
    local status=$1
    local message=$2
    local details=$3

    TOTAL_CHECKS=$((TOTAL_CHECKS + 1))

    case $status in
        PASS)
            echo -e "${GREEN}✓ PASS${NC} $message"
            PASS_COUNT=$((PASS_COUNT + 1))
            CHECK_RESULTS+=("PASS: $message")
            ;;
        FAIL)
            echo -e "${RED}✗ FAIL${NC} $message"
            if [ -n "$details" ]; then
                echo -e "  ${RED}→${NC} $details"
            fi
            FAIL_COUNT=$((FAIL_COUNT + 1))
            CHECK_RESULTS+=("FAIL: $message")
            ;;
        WARN)
            echo -e "${YELLOW}⚠ WARN${NC} $message"
            if [ -n "$details" ]; then
                echo -e "  ${YELLOW}→${NC} $details"
            fi
            WARN_COUNT=$((WARN_COUNT + 1))
            CHECK_RESULTS+=("WARN: $message")
            ;;
    esac
}

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo -e "${RED}Please run as root (use sudo)${NC}"
    exit 1
fi

echo -e "${BLUE}${BOLD}"
echo "╔════════════════════════════════════════════════════════╗"
echo "║     OK Monitor Deployment Verification v1.0            ║"
echo "╚════════════════════════════════════════════════════════╝"
echo -e "${NC}"
echo ""

# ============================================================
# CHECK 1: Installation Directory
# ============================================================
echo -e "${BOLD}[1/12] Checking installation directory...${NC}"
if [ -d "$INSTALL_DIR" ]; then
    if [ -f "$INSTALL_DIR/device/main.py" ]; then
        check_result PASS "Installation directory exists with device code"
    else
        check_result FAIL "Installation directory exists but device code missing" \
            "Expected: $INSTALL_DIR/device/main.py"
    fi
else
    check_result FAIL "Installation directory not found" \
        "Expected: $INSTALL_DIR"
fi
echo ""

# ============================================================
# CHECK 2: Configuration File
# ============================================================
echo -e "${BOLD}[2/12] Checking configuration file...${NC}"
if [ -f "$ENV_FILE" ]; then
    check_result PASS "Configuration file exists"

    # Check for required variables
    API_URL=$(grep "^API_URL=" "$ENV_FILE" | cut -d'=' -f2 | tr -d ' "' || echo "")
    DEVICE_ID=$(grep "^DEVICE_ID=" "$ENV_FILE" | cut -d'=' -f2 | tr -d ' "' || echo "")
    CAMERA_SOURCE=$(grep "^CAMERA_SOURCE=" "$ENV_FILE" | cut -d'=' -f2 | tr -d ' "' || echo "")

    if [ -z "$API_URL" ]; then
        check_result FAIL "API_URL not set in configuration" \
            "Edit: sudo nano $ENV_FILE"
    else
        check_result PASS "API_URL configured: $API_URL"
    fi

    if [ -z "$DEVICE_ID" ] || [ "$DEVICE_ID" = "PLACEHOLDER_DEVICE_ID" ]; then
        check_result FAIL "DEVICE_ID not set or still placeholder" \
            "Run: sudo deployment/customize_clone.sh"
    else
        check_result PASS "DEVICE_ID configured: $DEVICE_ID"
    fi
else
    check_result FAIL "Configuration file not found" \
        "Expected: $ENV_FILE"
fi
echo ""

# ============================================================
# CHECK 3: Python Virtual Environment
# ============================================================
echo -e "${BOLD}[3/12] Checking Python virtual environment...${NC}"
if [ -d "$INSTALL_DIR/venv" ]; then
    if [ -f "$INSTALL_DIR/venv/bin/python" ]; then
        PYTHON_VERSION=$("$INSTALL_DIR/venv/bin/python" --version 2>&1)
        check_result PASS "Virtual environment exists ($PYTHON_VERSION)"
    else
        check_result FAIL "Virtual environment exists but Python not found"
    fi
else
    check_result FAIL "Virtual environment not found" \
        "Expected: $INSTALL_DIR/venv"
fi
echo ""

# ============================================================
# CHECK 4: Service Status
# ============================================================
echo -e "${BOLD}[4/12] Checking systemd service...${NC}"
if systemctl list-unit-files | grep -q "$SERVICE_NAME.service"; then
    check_result PASS "Service file installed"

    if systemctl is-enabled --quiet "$SERVICE_NAME" 2>/dev/null; then
        check_result PASS "Service enabled (auto-start on boot)"
    else
        check_result WARN "Service not enabled for auto-start" \
            "Run: sudo systemctl enable $SERVICE_NAME"
    fi

    if systemctl is-active --quiet "$SERVICE_NAME"; then
        check_result PASS "Service is running"

        # Check if service has been running for at least 30 seconds
        UPTIME=$(systemctl show -p ActiveEnterTimestampMonotonic "$SERVICE_NAME" | cut -d= -f2)
        NOW=$(date +%s%N | cut -b1-16)
        if [ -n "$UPTIME" ] && [ "$UPTIME" != "0" ]; then
            RUNTIME=$(( (NOW - UPTIME) / 1000000 ))
            if [ $RUNTIME -gt 30000 ]; then
                check_result PASS "Service stable (running for ${RUNTIME}ms)"
            else
                check_result WARN "Service just started (${RUNTIME}ms)" \
                    "Monitor: sudo journalctl -u $SERVICE_NAME -f"
            fi
        fi
    else
        check_result FAIL "Service is not running" \
            "Start: sudo systemctl start $SERVICE_NAME"
    fi
else
    check_result FAIL "Service file not installed" \
        "Expected: /etc/systemd/system/$SERVICE_NAME.service"
fi
echo ""

# ============================================================
# CHECK 5: Update Timer
# ============================================================
echo -e "${BOLD}[5/12] Checking update timer...${NC}"
if systemctl list-unit-files | grep -q "okmonitor-update.timer"; then
    check_result PASS "Update timer installed"

    if systemctl is-enabled --quiet okmonitor-update.timer 2>/dev/null; then
        check_result PASS "Update timer enabled"

        # Check next scheduled run
        NEXT_RUN=$(systemctl list-timers okmonitor-update.timer --no-pager | grep okmonitor-update | awk '{print $1, $2, $3}' || echo "")
        if [ -n "$NEXT_RUN" ]; then
            check_result PASS "Next update scheduled: $NEXT_RUN"
        fi
    else
        check_result WARN "Update timer not enabled" \
            "Run: sudo systemctl enable okmonitor-update.timer"
    fi
else
    check_result WARN "Update timer not installed" \
        "Updates will not happen automatically"
fi
echo ""

# ============================================================
# CHECK 6: Camera Accessibility
# ============================================================
echo -e "${BOLD}[6/12] Checking camera...${NC}"
if ls /dev/video* >/dev/null 2>&1; then
    CAMERA_COUNT=$(ls /dev/video* 2>/dev/null | wc -l)
    check_result PASS "Found $CAMERA_COUNT camera device(s)"

    # Check specific camera source from config
    if [ -n "$CAMERA_SOURCE" ]; then
        CAMERA_DEV="/dev/video$CAMERA_SOURCE"
        if [ -e "$CAMERA_DEV" ]; then
            check_result PASS "Configured camera exists: $CAMERA_DEV"

            # Check permissions
            if [ -r "$CAMERA_DEV" ] && [ -w "$CAMERA_DEV" ]; then
                check_result PASS "Camera device is accessible"
            else
                check_result FAIL "Camera device exists but not accessible" \
                    "Check permissions on $CAMERA_DEV"
            fi
        else
            check_result FAIL "Configured camera not found: $CAMERA_DEV" \
                "Update CAMERA_SOURCE in $ENV_FILE"
        fi
    fi

    # List all cameras
    echo "  Available cameras:"
    v4l2-ctl --list-devices 2>/dev/null | head -20 | sed 's/^/    /'
else
    check_result FAIL "No camera devices found" \
        "Connect USB webcam and check with: v4l2-ctl --list-devices"
fi
echo ""

# ============================================================
# CHECK 7: User Permissions
# ============================================================
echo -e "${BOLD}[7/12] Checking user permissions...${NC}"
# Detect service user
SERVICE_USER=$(systemctl show -p User "$SERVICE_NAME" 2>/dev/null | cut -d= -f2)
if [ -z "$SERVICE_USER" ] || [ "$SERVICE_USER" = "[not set]" ]; then
    SERVICE_USER="mok"  # fallback
fi

if id "$SERVICE_USER" >/dev/null 2>&1; then
    check_result PASS "Service user exists: $SERVICE_USER"

    # Check video group membership
    if groups "$SERVICE_USER" | grep -q video; then
        check_result PASS "User $SERVICE_USER in 'video' group"
    else
        check_result FAIL "User $SERVICE_USER not in 'video' group" \
            "Run: sudo usermod -a -G video $SERVICE_USER && sudo reboot"
    fi

    # Check ownership of install directory
    OWNER=$(stat -c '%U' "$INSTALL_DIR" 2>/dev/null || echo "unknown")
    if [ "$OWNER" = "$SERVICE_USER" ] || [ "$OWNER" = "root" ]; then
        check_result PASS "Install directory ownership correct"
    else
        check_result WARN "Install directory owned by $OWNER, expected $SERVICE_USER" \
            "May cause permission issues"
    fi
else
    check_result FAIL "Service user not found: $SERVICE_USER"
fi
echo ""

# ============================================================
# CHECK 8: Network Connectivity
# ============================================================
echo -e "${BOLD}[8/12] Checking network connectivity...${NC}"
if ping -c 1 -W 2 8.8.8.8 >/dev/null 2>&1; then
    check_result PASS "Internet connectivity (ping 8.8.8.8)"
else
    check_result FAIL "No internet connectivity" \
        "Check network connection or configure WiFi: ~/addwifi.sh"
fi

if [ -n "$API_URL" ]; then
    # Extract domain from API_URL
    API_DOMAIN=$(echo "$API_URL" | sed -E 's|https?://||' | cut -d'/' -f1)

    if curl -s --head --connect-timeout 5 "$API_URL/health" >/dev/null 2>&1; then
        check_result PASS "Cloud API reachable: $API_URL"
    else
        check_result FAIL "Cloud API not reachable: $API_URL" \
            "Check API_URL in $ENV_FILE or network connectivity"
    fi
fi
echo ""

# ============================================================
# CHECK 9: Service Logs
# ============================================================
echo -e "${BOLD}[9/12] Checking service logs...${NC}"
if journalctl -u "$SERVICE_NAME" -n 1 --no-pager >/dev/null 2>&1; then
    # Check for recent errors
    ERROR_COUNT=$(journalctl -u "$SERVICE_NAME" --since "5 minutes ago" --no-pager 2>/dev/null | grep -i error | wc -l)

    if [ "$ERROR_COUNT" -eq 0 ]; then
        check_result PASS "No recent errors in logs (last 5 minutes)"
    elif [ "$ERROR_COUNT" -lt 3 ]; then
        check_result WARN "$ERROR_COUNT error(s) in logs (last 5 minutes)" \
            "Check: sudo journalctl -u $SERVICE_NAME -n 50"
    else
        check_result FAIL "$ERROR_COUNT errors in logs (last 5 minutes)" \
            "Check: sudo journalctl -u $SERVICE_NAME -n 50"
    fi

    # Show last log line
    LAST_LOG=$(journalctl -u "$SERVICE_NAME" -n 1 --no-pager 2>/dev/null | tail -1)
    if [ -n "$LAST_LOG" ]; then
        echo "  Last log: ${LAST_LOG:0:100}"
    fi
else
    check_result WARN "Could not read service logs"
fi
echo ""

# ============================================================
# CHECK 10: Disk Space
# ============================================================
echo -e "${BOLD}[10/12] Checking disk space...${NC}"
DISK_USAGE=$(df -h "$INSTALL_DIR" | awk 'NR==2 {print $5}' | sed 's/%//')
DISK_AVAIL=$(df -h "$INSTALL_DIR" | awk 'NR==2 {print $4}')

if [ "$DISK_USAGE" -lt 80 ]; then
    check_result PASS "Disk usage OK: ${DISK_USAGE}% used, $DISK_AVAIL available"
elif [ "$DISK_USAGE" -lt 90 ]; then
    check_result WARN "Disk usage high: ${DISK_USAGE}% used, $DISK_AVAIL available" \
        "Consider cleaning debug captures"
else
    check_result FAIL "Disk almost full: ${DISK_USAGE}% used, $DISK_AVAIL available" \
        "Clean up: find /opt/okmonitor/debug_captures -mtime +7 -delete"
fi
echo ""

# ============================================================
# CHECK 11: Tailscale (Optional)
# ============================================================
echo -e "${BOLD}[11/12] Checking Tailscale (optional)...${NC}"
if command -v tailscale >/dev/null 2>&1; then
    check_result PASS "Tailscale installed"

    if tailscale status >/dev/null 2>&1; then
        TS_HOSTNAME=$(tailscale status --json 2>/dev/null | grep -o '"HostName":"[^"]*"' | cut -d'"' -f4 | head -1 || echo "unknown")
        TS_IP=$(tailscale ip -4 2>/dev/null || echo "unknown")
        check_result PASS "Tailscale connected: $TS_HOSTNAME ($TS_IP)"
    else
        check_result WARN "Tailscale not connected" \
            "Connect: sudo deployment/install_tailscale.sh --auth-key YOUR_KEY"
    fi
else
    check_result WARN "Tailscale not installed (optional)" \
        "Install for remote access: sudo deployment/install_tailscale.sh"
fi
echo ""

# ============================================================
# CHECK 12: WiFi Status (if wireless)
# ============================================================
echo -e "${BOLD}[12/12] Checking WiFi (if applicable)...${NC}"
if nmcli device status | grep -q "^wlan.*connected"; then
    WIFI_SSID=$(nmcli -t -f active,ssid dev wifi | grep '^yes' | cut -d: -f2)
    WIFI_SIGNAL=$(nmcli -t -f active,signal dev wifi | grep '^yes' | cut -d: -f2)

    if [ -n "$WIFI_SSID" ]; then
        if [ "$WIFI_SIGNAL" -gt 50 ]; then
            check_result PASS "WiFi connected: $WIFI_SSID (signal: $WIFI_SIGNAL%)"
        else
            check_result WARN "WiFi connected but weak signal: $WIFI_SSID ($WIFI_SIGNAL%)" \
                "Consider repositioning device or adding extender"
        fi
    fi
elif ip link show eth0 2>/dev/null | grep -q "state UP"; then
    check_result PASS "Using Ethernet connection (eth0)"
else
    check_result WARN "No active WiFi or Ethernet connection detected"
fi
echo ""

# ============================================================
# SUMMARY
# ============================================================
echo ""
echo -e "${BLUE}${BOLD}"
echo "╔════════════════════════════════════════════════════════╗"
echo "║                  VERIFICATION SUMMARY                   ║"
echo "╚════════════════════════════════════════════════════════╝"
echo -e "${NC}"
echo ""

echo -e "${GREEN}✓ Passed:  $PASS_COUNT${NC}"
echo -e "${YELLOW}⚠ Warnings: $WARN_COUNT${NC}"
echo -e "${RED}✗ Failed:  $FAIL_COUNT${NC}"
echo -e "  ${BOLD}Total:   $TOTAL_CHECKS${NC}"
echo ""

# Overall status
if [ $FAIL_COUNT -eq 0 ] && [ $WARN_COUNT -eq 0 ]; then
    echo -e "${GREEN}${BOLD}🎉 EXCELLENT! Device is fully configured and ready for production.${NC}"
    echo ""
    EXIT_CODE=0
elif [ $FAIL_COUNT -eq 0 ]; then
    echo -e "${YELLOW}${BOLD}⚠ GOOD with warnings. Device should work but review warnings above.${NC}"
    echo ""
    EXIT_CODE=0
else
    echo -e "${RED}${BOLD}✗ ISSUES FOUND. Please address failures above before deployment.${NC}"
    echo ""
    EXIT_CODE=1
fi

# Next steps
if [ $FAIL_COUNT -gt 0 ]; then
    echo -e "${BOLD}Next Steps:${NC}"
    echo "  1. Review failures above and fix issues"
    echo "  2. Run this script again: sudo deployment/verify_deployment.sh"
    echo "  3. Check logs: sudo journalctl -u $SERVICE_NAME -f"
    echo ""
fi

# Useful commands
echo -e "${BOLD}Useful Commands:${NC}"
echo "  View logs:       sudo journalctl -u $SERVICE_NAME -f"
echo "  Restart service: sudo systemctl restart $SERVICE_NAME"
echo "  Edit config:     sudo nano $ENV_FILE"
echo "  Add WiFi:        ~/addwifi.sh \"SSID\" \"password\""
echo "  Manual update:   sudo /opt/okmonitor/deployment/update_device.sh"
echo ""

exit $EXIT_CODE
