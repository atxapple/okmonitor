# Quick Start: Route 2 - Golden Image Cloning

**Print and laminate this guide for field technicians**

---

## Overview

This route clones a pre-configured SD card image to quickly deploy multiple devices.

**Time per device:** ~5 minutes (after golden image created)

---

## Part A: Create Golden Image (One-Time Setup)

**Do this ONCE to create the master image**

### Before You Start
- ☐ One Raspberry Pi 5 set up as master device
- ☐ Master device tested and working perfectly
- ☐ Computer with SD card reader
- ☐ Imaging software installed (Win32DiskImager, dd, or Balena Etcher)

---

### 1. Prepare Master Device
```bash
# SSH into master device
ssh mok@okmonitor.local

# Stop service
sudo systemctl stop okmonitor-device

# Prepare for cloning
sudo deployment/prepare_for_clone.sh

# Shutdown
sudo shutdown -h now
```
☐ Master device prepared

---

### 2. Create SD Card Image

**On Windows:**
1. Download Win32 Disk Imager
2. Insert master SD card
3. Click "Read"
4. Save as: `okmonitor-golden-v1.0.img`

**On macOS:**
```bash
diskutil list
diskutil unmountDisk /dev/disk2
sudo dd if=/dev/rdisk2 of=~/okmonitor-golden-v1.0.img bs=4m status=progress
```

**On Linux:**
```bash
lsblk
sudo dd if=/dev/sdb of=~/okmonitor-golden-v1.0.img bs=4M status=progress
```

☐ Image created

---

### 3. (Optional) Shrink Image
```bash
# Download PiShrink
wget https://raw.githubusercontent.com/Drewsif/PiShrink/master/pishrink.sh
chmod +x pishrink.sh

# Shrink image
sudo ./pishrink.sh okmonitor-golden-v1.0.img
```
☐ Image optimized

---

## Part B: Deploy to New Devices

**Do this for EACH device**

### Before You Start
- ☐ Golden image file ready
- ☐ Blank SD card (32GB+)
- ☐ Unique device ID chosen for this device
- ☐ WiFi credentials (if needed)
- ☐ Tailscale auth key (if needed)

---

### 1. Write Image to SD Card

**Using Balena Etcher (Easiest):**
1. Download: https://etcher.balena.io/
2. Select golden image file
3. Select SD card
4. Click "Flash"

**Using dd (Linux/macOS):**
```bash
sudo dd if=okmonitor-golden-v1.0.img of=/dev/sdX bs=4M status=progress
sync
```

**Using Win32DiskImager (Windows):**
1. Select golden image file
2. Select SD card drive
3. Click "Write"

☐ Image written to SD card

---

### 2. Boot Device
1. Insert SD card into Raspberry Pi
2. Connect power
3. Wait ~60 seconds for boot
4. Connect via SSH

```bash
ssh mok@okmonitor.local
# Default password from golden image
```

☐ Device booted and accessible

---

### 3. Customize Device ID

```bash
# Run customization script
sudo deployment/customize_clone.sh
```

**When prompted:**
- Enter unique DEVICE_ID: `okmonitor1` (or `floor-01-cam`, etc.)
- Confirm: `y`
- **Connect to Tailscale?** `y` (recommended)
  - Enter Tailscale auth key when prompted
  - Or press `n` to skip (can connect later)

**Script will:**
- Update device configuration
- Clear cached data
- Reset Tailscale identity
- **Prompt to connect Tailscale**
- Restart service

☐ Device customized with unique ID
☐ Tailscale connected (if accepted prompt)

---

### 4. Configure WiFi (if needed)

**Method A: Comitup Web Interface** (Recommended for field deployment - no SSH needed!)
```bash
# 1. Reboot device: sudo reboot
# 2. Connect phone/laptop to 'okmonitor-XXXX' WiFi (no password)
# 3. Open browser to: http://10.41.0.1
# 4. Select customer WiFi and enter password
# Device automatically connects and starts monitoring!
```
📖 **Full guide:** [COMITUP.md](COMITUP.md) or [ONSITE-SETUP.md](ONSITE-SETUP.md)

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

### 5. Connect Tailscale (if skipped in step 3)

```bash
# If you skipped Tailscale during customization:
sudo deployment/install_tailscale.sh --auth-key tskey-auth-xxxxx

# Verify
tailscale status
```

☐ Tailscale connected (if skipped earlier)

**Note:** Tailscale is pre-installed in golden image - this step only connects if you skipped the prompt

---

### 6. Verify Deployment

```bash
# Run verification
sudo deployment/verify_deployment.sh
```

**Expected:** All checks pass

**Check logs:**
```bash
sudo journalctl -u okmonitor-device -f
```

**You should see:**
```
[device] Entering scheduled capture mode...
[device] Received new config: {...}
[device] Camera opened successfully
```

☐ Verification passed

---

### 7. Final Checks

```bash
# Test reboot
sudo reboot
```

**After reboot:**
```bash
# Wait 1 minute, reconnect
ssh mok@device-hostname
sudo systemctl status okmonitor-device
```

☐ Auto-start verified

---

## Batch Deployment Workflow

**For deploying 10+ devices efficiently:**

### Step 1: Write All SD Cards
```
1. Write golden image to first SD card
2. Label SD card with device ID
3. Repeat for all devices
4. Stack labeled cards
```

### Step 2: Boot and Customize
```
For each device:
  1. Insert SD card
  2. Boot device
  3. SSH in
  4. Run: sudo deployment/customize_clone.sh
  5. Enter device ID from label
  6. Configure WiFi (if needed)
  7. Move to next device
```

### Step 3: Bulk Tailscale Setup
```bash
# After all devices customized, from management PC:
DEVICES=("okmonitor1" "okmonitor2" "okmonitor3")
AUTH_KEY="tskey-auth-xxxxx"

for device in "${DEVICES[@]}"; do
    ssh mok@okmonitor-$device.local \
        "sudo deployment/install_tailscale.sh --auth-key $AUTH_KEY"
done
```

---

## Quick Reference Commands

| Task | Command |
|------|---------|
| Customize clone | `sudo deployment/customize_clone.sh` |
| View logs | `sudo journalctl -u okmonitor-device -f` |
| Restart service | `sudo systemctl restart okmonitor-device` |
| Edit config | `sudo nano /opt/okmonitor/.env.device` |
| Add WiFi | `~/addwifi.sh "SSID" "password"` |
| Verify deployment | `sudo deployment/verify_deployment.sh` |
| Check device ID | `grep DEVICE_ID /opt/okmonitor/.env.device` |

---

## Troubleshooting

### Device ID Still Placeholder
```bash
sudo deployment/customize_clone.sh
# Or manually:
sudo nano /opt/okmonitor/.env.device
# Change DEVICE_ID line, then:
sudo systemctl restart okmonitor-device
```

### Service Won't Start
```bash
sudo journalctl -u okmonitor-device -n 50
sudo systemctl status okmonitor-device
```
**Common fixes:**
- Camera not connected → Check USB
- Device ID still placeholder → Run customize script
- No internet → Configure WiFi

### Tailscale Conflict
```bash
# If "node already registered" error:
sudo tailscale logout
sudo deployment/install_tailscale.sh --auth-key YOUR_KEY
```

### Multiple Devices Same ID
```bash
# On duplicate device:
sudo deployment/customize_clone.sh
# Enter NEW unique device ID
```

---

## Device Naming Best Practices

**Good examples:**
- `floor-01-cam` - Clear location
- `warehouse-entrance` - Clear purpose
- `lab-02-bench-01` - Specific location

**Bad examples:**
- `cam1` - Too generic
- `test` - Not descriptive
- `device-ABC123` - Not readable

---

## Completion Checklist

Before leaving the site:

- ☐ Golden image written to SD card
- ☐ Device booted successfully
- ☐ Customize script run with unique ID
- ☐ Service running (`sudo systemctl status okmonitor-device`)
- ☐ Camera working (check logs)
- ☐ Cloud connected (verify script passed)
- ☐ WiFi configured (if applicable)
- ☐ Tailscale connected (if needed)
- ☐ Auto-start verified (reboot test passed)
- ☐ Device ID label applied to hardware
- ☐ Device ID recorded in tracking sheet
- ☐ Customer notified

---

## Golden Image Version Tracking

**Current image version:** _______________
**Image creation date:** _______________
**What's included:**
- ☐ OK Monitor device software
- ☐ WiFi management tool
- ☐ Tailscale (optional)
- ☐ Auto-update configured
- ☐ All dependencies

**Image file location:** _____________________________________

---

## Support

**Detailed guide:** [CLONING.md](CLONING.md)

**Issue?**
1. Run: `sudo deployment/verify_deployment.sh`
2. Check logs: `sudo journalctl -u okmonitor-device -f`
3. Review: [CLONING.md#troubleshooting](CLONING.md#troubleshooting)

---

## Deployment Record

**Deployment Date:** _______________
**Device ID:** _______________
**Golden Image Version:** _______________
**WiFi Network:** _______________
**Tailscale Hostname:** _______________
**Technician:** _______________
**Site Location:** _____________________________________
**Notes:** _____________________________________
_____________________________________
