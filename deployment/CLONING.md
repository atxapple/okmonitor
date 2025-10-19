# SD Card Cloning Guide - Route 2: Golden Image Deployment

**📖 Start here:** [Main Deployment README](README.md) - Choose Route 1 or Route 2
**⚡ Quick guide:** [QUICK-START-ROUTE2.md](QUICK-START-ROUTE2.md) - Condensed instructions

---

This guide covers **Route 2: Golden Image Cloning** - creating a "golden image" from a fully configured device and cloning it to multiple Raspberry Pis for fleet deployment.

## Overview

**Strategy:** Set up one perfect device → Clone SD card → Customize each clone

**Benefits:**
- ✅ Consistent configuration across fleet
- ✅ Faster deployment (minutes vs hours per device)
- ✅ Pre-tested software stack
- ✅ Reduced human error
- ✅ Easy to update entire fleet

---

## Part 1: Create the Golden Image

### Step 1: Set Up Master Device

Install and configure everything on your first Raspberry Pi:

```bash
# 1. Fresh Raspberry Pi OS installation
# 2. Run device installer
sudo deployment/install_device.sh

# 3. Configure device with PLACEHOLDER values
sudo nano /opt/okmonitor/.env.device
```

**IMPORTANT:** Use placeholder values for device-specific settings:

```bash
# /opt/okmonitor/.env.device - Golden Image Template
API_URL=https://okmonitor-production.up.railway.app
DEVICE_ID=PLACEHOLDER_DEVICE_ID    # ← Will be customized per device
CAMERA_SOURCE=0
CAMERA_WARMUP=3
API_TIMEOUT=30
CONFIG_POLL_INTERVAL=5.0
SAVE_FRAMES_DIR=
```

### Step 2: Install Optional Services

If using Tailscale for remote access:

```bash
# Install Tailscale (but DON'T connect yet)
sudo deployment/install_tailscale.sh
# When prompted, CANCEL or skip authentication
# We'll authenticate each clone individually
```

**OR** if you want Tailscale pre-configured, you can connect with an ephemeral key (device will disappear when cloned).

### Step 3: Test Everything

```bash
# Test camera
v4l2-ctl --list-devices

# Test WiFi script
~/addwifi.sh --help

# Check services (they may fail due to PLACEHOLDER_DEVICE_ID, that's OK)
sudo systemctl status okmonitor-device

# Verify all files are in place
ls -la /opt/okmonitor/
ls -la ~/addwifi.sh
```

### Step 4: Prepare for Cloning

```bash
# Clear any device-specific data
sudo systemctl stop okmonitor-device
sudo rm -rf /opt/okmonitor/debug_captures/*
sudo rm -rf /opt/okmonitor/config/*

# Clear shell history (optional, for security)
history -c
cat /dev/null > ~/.bash_history

# Clear logs (optional, reduces image size)
sudo journalctl --rotate
sudo journalctl --vacuum-time=1s

# Shutdown cleanly
sudo shutdown -h now
```

### Step 5: Create the Image

Remove the SD card and create a backup image on your computer.

**On Windows:**
1. Download Win32 Disk Imager: https://sourceforge.net/projects/win32diskimager/
2. Insert SD card
3. Click "Read"
4. Save as: `okmonitor-golden-image.img`

**On macOS:**
```bash
# Find the disk
diskutil list

# Unmount (not eject!)
diskutil unmountDisk /dev/disk2

# Create image
sudo dd if=/dev/rdisk2 of=~/okmonitor-golden-image.img bs=4m status=progress

# Compress to save space (optional)
gzip ~/okmonitor-golden-image.img
```

**On Linux:**
```bash
# Find the disk
lsblk

# Create image
sudo dd if=/dev/sdb of=~/okmonitor-golden-image.img bs=4M status=progress conv=fsync

# Compress to save space (optional)
gzip ~/okmonitor-golden-image.img
```

**Pro Tip:** Use PiShrink to reduce image size:
```bash
# Download PiShrink
wget https://raw.githubusercontent.com/Drewsif/PiShrink/master/pishrink.sh
chmod +x pishrink.sh

# Shrink the image
sudo ./pishrink.sh okmonitor-golden-image.img

# Result: Much smaller image that auto-expands on first boot
```

---

## Part 2: Clone to New Devices

### Step 1: Write Image to New SD Cards

**On Windows (Win32 Disk Imager):**
1. Insert new SD card
2. Select `okmonitor-golden-image.img`
3. Click "Write"
4. Wait for completion

**On macOS:**
```bash
# Unmount the new SD card
diskutil unmountDisk /dev/disk2

# Write image
sudo dd if=~/okmonitor-golden-image.img of=/dev/rdisk2 bs=4m status=progress

# Or if compressed:
gunzip -c ~/okmonitor-golden-image.img.gz | sudo dd of=/dev/rdisk2 bs=4m status=progress

# Eject
diskutil eject /dev/disk2
```

**On Linux:**
```bash
# Write image
sudo dd if=~/okmonitor-golden-image.img of=/dev/sdb bs=4M status=progress conv=fsync

# Or if compressed:
gunzip -c ~/okmonitor-golden-image.img.gz | sudo dd of=/dev/sdb bs=4M status=progress conv=fsync

# Sync and eject
sync
sudo eject /dev/sdb
```

**Pro Tip:** Use Balena Etcher for easier flashing:
- Download: https://etcher.balena.io/
- Works on Windows/macOS/Linux
- User-friendly GUI
- Validates written data

### Step 2: Boot and Customize Each Device

Insert SD card into Raspberry Pi and boot:

```bash
# 1. Connect via Ethernet or existing WiFi
ssh mok@raspberrypi.local

# 2. (Optional) Change hostname for easy identification
sudo raspi-config
# → System Options → Hostname → e.g., "okmonitor-site1"
# Or via command:
sudo hostnamectl set-hostname okmonitor-site1

# 3. Update device ID
sudo deployment/customize_clone.sh

# This script will prompt you for:
# - New DEVICE_ID (e.g., okmonitor1, floor-01-cam, warehouse-entrance)
# - Restart services automatically
```

**Manual customization (if script not available):**
```bash
# Edit device configuration
sudo nano /opt/okmonitor/.env.device
# Change: DEVICE_ID=PLACEHOLDER_DEVICE_ID
# To: DEVICE_ID=okmonitor1  (or your chosen ID)

# Restart service
sudo systemctl restart okmonitor-device

# Verify it's working
sudo journalctl -u okmonitor-device -f
```

### Step 3: Configure WiFi (if needed)

```bash
# Add site-specific WiFi
~/addwifi.sh "Site-WiFi-Name" "wifi-password" 200

# Verify connection
ip addr show wlan0
ping -c 3 8.8.8.8
```

### Step 4: Set Up Tailscale (if needed)

```bash
# Connect to Tailscale (uses device ID from .env.device)
sudo deployment/install_tailscale.sh --auth-key tskey-auth-xxxxx

# Or if already installed, just connect:
sudo tailscale up --authkey=tskey-auth-xxxxx --hostname=okmonitor-okmonitor1
```

### Step 5: Verify Everything Works

```bash
# Run automated verification
sudo deployment/verify_deployment.sh

# Check device service
sudo systemctl status okmonitor-device

# Check camera
v4l2-ctl --list-devices

# Check cloud connectivity
curl https://okmonitor-production.up.railway.app/health

# View live logs
sudo journalctl -u okmonitor-device -f
```

---

## Part 3: Batch Cloning Workflow

### For Multiple Devices

**Efficient process for cloning 10+ devices:**

1. **Prepare materials:**
   - Golden image file
   - Stack of blank SD cards (same size or larger)
   - SD card reader/writer
   - List of device IDs

2. **Write all SD cards:**
   ```bash
   # Use Balena Etcher or dd to write all cards
   # Label each card with intended device ID
   ```

3. **Boot and customize in assembly-line fashion:**
   ```bash
   # Device 1
   ssh mok@raspberrypi.local
   sudo deployment/customize_clone.sh
   # Enter: okmonitor1
   # Configure WiFi if needed

   # Device 2
   ssh mok@raspberrypi.local
   sudo deployment/customize_clone.sh
   # Enter: okmonitor2
   # Configure WiFi if needed

   # Continue for all devices...
   ```

4. **Bulk Tailscale setup** (after all devices customized):
   ```bash
   # From your management machine
   DEVICES=("okmonitor1" "okmonitor2" "okmonitor3")
   AUTH_KEY="tskey-auth-xxxxx"

   for id in "${DEVICES[@]}"; do
       ssh mok@okmonitor-$id.local "sudo deployment/install_tailscale.sh --auth-key $AUTH_KEY"
   done
   ```

---

## Part 4: Maintenance & Updates

### Update Golden Image

When you want to update the entire fleet with new software:

1. **Update one device:**
   ```bash
   ssh mok@okmonitor-okmonitor1
   cd /opt/okmonitor
   git pull
   sudo systemctl restart okmonitor-device
   ```

2. **Test thoroughly:**
   - Verify captures are working
   - Check cloud connectivity
   - Monitor for errors

3. **Create new golden image:**
   ```bash
   # On the updated device
   sudo systemctl stop okmonitor-device
   sudo deployment/prepare_for_clone.sh  # See below
   sudo shutdown -h now

   # On your computer
   # Create new image: okmonitor-golden-image-v2.img
   ```

4. **Deploy to fleet:**
   - Either clone new devices from v2 image
   - Or update existing devices via git pull (easier!)

### Rolling Updates (Recommended)

Instead of re-cloning, use the built-in update mechanism:

```bash
# Update happens automatically at 2:00 AM via okmonitor-update.timer

# Or manually trigger update on all devices:
DEVICES=("okmonitor-okmonitor1" "okmonitor-okmonitor2" "okmonitor-okmonitor3")

for device in "${DEVICES[@]}"; do
    echo "Updating $device..."
    ssh mok@$device 'cd /opt/okmonitor && git pull && sudo systemctl restart okmonitor-device'
done
```

This is much faster than re-imaging!

---

## Part 5: Helper Scripts

### customize_clone.sh

Already included in the repository at `deployment/customize_clone.sh`.

**Usage:**
```bash
sudo deployment/customize_clone.sh
```

**What it does:**
- Prompts for new device ID
- Updates .env.device configuration
- Clears cached data and debug captures
- Logs out of Tailscale (each clone needs unique identity)
- Restarts services
- Provides next-step instructions

### prepare_for_clone.sh

Create this script to prepare a device before imaging:

```bash
#!/bin/bash
# deployment/prepare_for_clone.sh
# Prepare device for cloning

set -e

echo "===== Preparing Device for Cloning ====="

# Stop services
sudo systemctl stop okmonitor-device

# Reset device ID to placeholder
sudo sed -i 's/^DEVICE_ID=.*/DEVICE_ID=PLACEHOLDER_DEVICE_ID/' /opt/okmonitor/.env.device

# Clear data
sudo rm -rf /opt/okmonitor/debug_captures/*
sudo rm -rf /opt/okmonitor/config/*

# Logout from Tailscale
if command -v tailscale &> /dev/null; then
    sudo tailscale logout 2>/dev/null || true
fi

# Clear logs
sudo journalctl --rotate
sudo journalctl --vacuum-time=1s

# Clear shell history
cat /dev/null > ~/.bash_history
history -c

echo "Device ready for cloning!"
echo "You can now shutdown and create an image."
```

---

## Part 6: Troubleshooting

### Clone Won't Boot

**Symptoms:** Raspberry Pi doesn't boot from cloned SD card

**Causes & Solutions:**

1. **SD card not written correctly:**
   - Re-write the image
   - Verify the image file is not corrupted
   - Try a different SD card

2. **SD card too small:**
   - Golden image was from larger card
   - Use PiShrink before cloning to reduce size
   - Or use same size/larger cards

3. **Corrupted image:**
   - Re-create golden image from original device
   - Verify hash: `sha256sum okmonitor-golden-image.img`

### Device ID Not Updating

**Symptoms:** Device still shows PLACEHOLDER_DEVICE_ID

**Solution:**
```bash
# Manually edit
sudo nano /opt/okmonitor/.env.device
# Change DEVICE_ID line

# Restart service
sudo systemctl restart okmonitor-device
```

### Services Failing After Clone

**Symptoms:** `okmonitor-device` service won't start

**Check logs:**
```bash
sudo journalctl -u okmonitor-device -n 50
```

**Common issues:**
- Device ID still placeholder → Run customize_clone.sh
- Camera not connected → Connect USB camera
- Network issues → Configure WiFi or connect Ethernet
- Cloud API unreachable → Check API_URL in .env.device

### Multiple Devices Same ID

**Symptoms:** Two devices with same DEVICE_ID causing conflicts

**Solution:**
```bash
# On the duplicate device
sudo deployment/customize_clone.sh
# Enter a unique ID
```

### Tailscale Conflicts

**Symptoms:** Can't connect to Tailscale, "node already registered" error

**Cause:** Cloned device has same Tailscale identity

**Solution:**
```bash
# Logout and re-authenticate
sudo tailscale logout
sudo deployment/install_tailscale.sh --auth-key YOUR_KEY
```

---

## Part 7: Best Practices

### Golden Image Management

1. **Version your images:**
   - `okmonitor-golden-v1.0-2024-10-19.img`
   - `okmonitor-golden-v1.1-2024-11-15.img`
   - Keep changelog of what's in each version

2. **Test before deploying:**
   - Clone to test device first
   - Verify all functionality
   - Then deploy to production fleet

3. **Keep images small:**
   - Use PiShrink to compress
   - Remove unnecessary packages before imaging
   - Clear all caches and temporary files

4. **Document configuration:**
   - What's installed
   - What needs customization per device
   - Default passwords (if any)

### Device Naming Convention

Use consistent, descriptive names:

**Good examples:**
- `floor-01-cam` - Clear location
- `warehouse-entrance` - Clear purpose
- `lab-02-bench-01` - Specific location
- `site-alpha-cam-01` - Site + sequence

**Bad examples:**
- `cam1` - Too generic
- `raspberry-pi-1` - Doesn't indicate purpose
- `test` - Not descriptive
- `device-A7B2C3` - Not human-readable

### Security Considerations

1. **Change default passwords before imaging:**
   ```bash
   passwd  # Change user password
   ```

2. **Don't include secrets in golden image:**
   - No WiFi passwords (add per-site)
   - No API keys (use environment variables)
   - No Tailscale auth keys (connect per-device)

3. **Unique identities per device:**
   - Different DEVICE_ID
   - Different Tailscale node
   - Different hostname (optional but recommended)

4. **Regular updates:**
   - Keep golden image updated with security patches
   - Or use rolling updates via git pull

---

## Part 8: Quick Reference

### Complete Workflow Summary

**One-time: Create Golden Image**
```bash
# 1. Set up perfect device
sudo deployment/install_device.sh

# 2. Test everything
sudo systemctl status okmonitor-device

# 3. Prepare for cloning
sudo deployment/prepare_for_clone.sh
sudo shutdown -h now

# 4. Create image (on your computer)
sudo dd if=/dev/rdisk2 of=okmonitor-golden.img bs=4m
./pishrink.sh okmonitor-golden.img
```

**Per Device: Clone and Customize**
```bash
# 1. Write image to SD card (on your computer)
# Use Balena Etcher or dd

# 2. Boot Raspberry Pi with new SD card

# 3. Customize (via SSH)
ssh mok@raspberrypi.local
sudo deployment/customize_clone.sh
# Enter unique device ID

# 4. Configure WiFi (if needed)
~/addwifi.sh "Site-WiFi" "password"

# 5. Connect Tailscale (if needed)
sudo deployment/install_tailscale.sh --auth-key YOUR_KEY

# 6. Verify
sudo journalctl -u okmonitor-device -f
```

### Useful Commands

```bash
# Check disk image size
ls -lh okmonitor-golden.img

# Verify SD card write
sudo dd if=/dev/rdisk2 | sha256sum

# Test clone before deploying
ssh mok@raspberrypi.local 'cat /opt/okmonitor/.env.device | grep DEVICE_ID'

# Bulk device check
for d in okmonitor1 okmonitor2 okmonitor3; do
    ssh mok@okmonitor-$d 'hostname && grep DEVICE_ID /opt/okmonitor/.env.device'
done
```

---

## Support

For issues with:
- **Cloning process**: Check troubleshooting section above
- **SD card tools**: See tool-specific documentation (Win32DiskImager, dd, Balena Etcher)
- **OK Monitor device**: See main DEPLOYMENT.md
- **Post-clone customization**: Run `customize_clone.sh` with verbose logging

---

Happy cloning! 🚀

<function_calls>
<invoke name="Read">
<parameter name="file_path">D:\dev\okmonitor\deployment\.env.device