# Quick Start: Route 1 - Fresh Installation

**Print and laminate this guide for field technicians**

---

## Before You Start

**What you need:**
- ☐ Raspberry Pi 5 with Raspberry Pi OS Bookworm installed
- ☐ SSH enabled (via raspi-config or Imager settings)
- ☐ Internet connection (Ethernet or WiFi)
- ☐ USB webcam connected
- ☐ Cloud API URL (e.g., `https://okmonitor-production.up.railway.app`)
- ☐ Device ID chosen (e.g., `okmonitor1`, `floor-01-cam`)

**Time required:** ~30 minutes

---

## Step-by-Step Installation

### 1. Connect to Device
```bash
# Find device IP (if using DHCP)
# Or use: okmonitor.local

ssh mok@okmonitor.local
# Enter password when prompted
```
☐ Connected via SSH

---

### 2. Clone Repository
```bash
cd ~
git clone https://github.com/atxapple/okmonitor.git
cd okmonitor
```
☐ Repository cloned

---

### 3. Configure Device Settings FIRST
```bash
# Create configuration directory
sudo mkdir -p /opt/okmonitor
sudo nano /opt/okmonitor/.env.device
```

**Enter these values:**
```bash
API_URL=https://okmonitor-production.up.railway.app
DEVICE_ID=okmonitor1                    # ← Change this! (used for Tailscale name)
CAMERA_SOURCE=0                         # Usually 0
```

**Save:** `Ctrl+O`, `Enter`, `Ctrl+X`

☐ Configuration created

---

### 4. Run Installer
```bash
sudo chmod +x deployment/install_device.sh

# With Tailscale (recommended - enables remote access)
sudo deployment/install_device.sh --tailscale-key tskey-auth-xxxxx

# Or without Tailscale (can add later)
sudo deployment/install_device.sh
```

**What this does:**
- Installs system dependencies
- Sets up Python environment
- Installs OK Monitor software
- Creates systemd services
- **Installs Comitup** (WiFi hotspot for easy on-site setup)
- Installs addwifi.sh (backup WiFi configuration tool)
- **Installs Tailscale** (uses DEVICE_ID from .env.device for hostname)

**Time:** ~15 minutes

☐ Installer completed

---

### 5. Configure WiFi (if needed)

**Method A: Comitup Web Interface** (Recommended for field deployment - no SSH needed!)
```bash
# 1. Reboot device: sudo reboot
# 2. Connect phone/laptop to 'okmonitor-XXXX' WiFi (no password)
# 3. Open browser to: http://10.41.0.1
# 4. Select customer WiFi and enter password
# Device automatically connects and starts monitoring!
```
📖 **Full guide:** [COMITUP.md](COMITUP.md)

**Method B: addwifi.sh Script** (Backup method with SSH access)
```bash
# Add WiFi network:
~/addwifi.sh "Network-Name" "wifi-password" 100

# Verify connection:
ping -c 3 8.8.8.8
```
📖 **Full guide:** [WIFI.md](WIFI.md)

☐ WiFi configured (if needed)

---

### 6. Start Service
```bash
# Start the service
sudo systemctl start okmonitor-device

# Watch logs (Ctrl+C to exit)
sudo journalctl -u okmonitor-device -f
```

**You should see:**
```
[device] Entering scheduled capture mode...
[device] Received new config: {...}
[device] Camera opened successfully
```

☐ Service started and running

---

### 7. Verify Installation
```bash
sudo deployment/verify_deployment.sh
```

**Expected:** All checks pass or only warnings

☐ Verification passed

---

### 8. Connect Tailscale (if not done in step 3)
```bash
# If you didn't use --tailscale-key during installation:
sudo deployment/install_tailscale.sh --auth-key tskey-auth-xxxxx

# Check status
tailscale status
```
☐ Tailscale connected

**Note:** Tailscale is already installed - this step only connects if you skipped it earlier

---

### 9. Final Checks
```bash
# Check service status
sudo systemctl status okmonitor-device

# Check update timer
sudo systemctl list-timers okmonitor-update

# Reboot test
sudo reboot
```

**After reboot:**
```bash
# Wait 1 minute, then check
ssh mok@okmonitor.local
sudo systemctl status okmonitor-device
```
☐ Auto-start verified

---

## Quick Reference Commands

| Task | Command |
|------|---------|
| View logs | `sudo journalctl -u okmonitor-device -f` |
| Restart service | `sudo systemctl restart okmonitor-device` |
| Edit config | `sudo nano /opt/okmonitor/.env.device` |
| Add WiFi | `~/addwifi.sh "SSID" "password"` |
| List cameras | `v4l2-ctl --list-devices` |
| Check API | `curl -I https://okmonitor-production.up.railway.app/health` |
| Manual update | `sudo /opt/okmonitor/deployment/update_device.sh` |
| Verify deployment | `sudo deployment/verify_deployment.sh` |

---

## Troubleshooting

### Service won't start
```bash
sudo journalctl -u okmonitor-device -n 50
sudo systemctl status okmonitor-device
```
**Common fixes:**
- Camera not connected → Check USB
- Wrong DEVICE_ID → Edit `.env.device`
- No internet → Configure WiFi or Ethernet

### Camera not found
```bash
v4l2-ctl --list-devices
ls -l /dev/video*
```
**Fix:** Update `CAMERA_SOURCE` in `/opt/okmonitor/.env.device`

### Network issues
```bash
curl -I https://okmonitor-production.up.railway.app/health
ping -c 4 8.8.8.8
```
**Fix:** Add WiFi with `~/addwifi.sh` or connect Ethernet

---

## Completion Checklist

Before leaving the site:

- ☐ Service running (`sudo systemctl status okmonitor-device`)
- ☐ Camera working (`v4l2-ctl --list-devices`)
- ☐ Cloud connected (`curl -I $API_URL/health`)
- ☐ WiFi configured (if applicable)
- ☐ Tailscale connected (if needed)
- ☐ Auto-start verified (reboot test passed)
- ☐ Device ID label applied to hardware
- ☐ Verification script passed
- ☐ Customer notified

---

## Support

**Detailed guide:** [DEPLOYMENT.md](DEPLOYMENT.md)

**Issue?**
1. Run: `sudo deployment/verify_deployment.sh`
2. Check logs: `sudo journalctl -u okmonitor-device -f`
3. Review: [DEPLOYMENT.md#troubleshooting](DEPLOYMENT.md#troubleshooting)

---

**Deployment Date:** _______________
**Device ID:** _______________
**Technician:** _______________
**Notes:** _____________________________________
