# OK Monitor Device Deployment Guide

Welcome! This guide helps you deploy OK Monitor devices on Raspberry Pi 5 hardware.

---

## 🎯 Choose Your Deployment Route

We support **two deployment methods**. Choose the one that fits your needs:

```
┌─────────────────────────────────────────────────────────────┐
│                  WHICH ROUTE SHOULD YOU USE?                │
└─────────────────────────────────────────────────────────────┘

   How many devices?
   ├─ 1-5 devices       →  Route 1: Fresh Installation
   └─ 10+ devices       →  Route 2: Golden Image Cloning

   Do you have on-site internet?
   ├─ Yes               →  Route 1 is fine
   └─ No/Unreliable     →  Route 2 recommended

   Need latest software version?
   ├─ Yes, always       →  Route 1 (pulls from git)
   └─ Consistent setup  →  Route 2 (frozen version)

   Technical expertise level?
   ├─ Comfortable with Linux  →  Either route works
   └─ Field technician        →  Route 2 (simpler)
```

---

## 📋 Route 1: Fresh Installation

**Install from scratch on vanilla Raspberry Pi OS**

**Time per device:** ~30 minutes
**Internet required:** Yes (during installation)
**Difficulty:** Medium
**Best for:** 1-5 devices, testing, custom setups

### Quick Overview

1. Start with fresh Raspberry Pi OS Bookworm (SSH/VNC enabled)
2. Clone repository
3. Run installation script
4. Configure device ID and camera
5. Test and verify

### Detailed Instructions

📖 **Full guide:** [DEPLOYMENT.md](DEPLOYMENT.md)
⚡ **Quick reference:** [QUICK-START-ROUTE1.md](QUICK-START-ROUTE1.md)

---

## 💾 Route 2: Golden Image Cloning

**Clone a pre-configured SD card image**

**Time per device:** ~5 minutes (after initial image creation)
**Internet required:** No (for cloning, yes for creating golden image)
**Difficulty:** Easy
**Best for:** 10+ devices, fleet deployment, on-site installations

### Quick Overview

**One-time setup:**
1. Use Route 1 to set up one perfect "golden" device
2. Prepare device for cloning
3. Create SD card image
4. Store image file for future deployments

**Per device:**
1. Write golden image to SD card
2. Boot device
3. Run customization script (sets unique device ID)
4. Configure WiFi (if needed)
5. Done!

### Detailed Instructions

📖 **Full guide:** [CLONING.md](CLONING.md)
⚡ **Quick reference:** [QUICK-START-ROUTE2.md](QUICK-START-ROUTE2.md)

---

## 📦 What's Included in Both Routes

Both deployment methods install:

- ✅ **OK Monitor device software** (camera capture and cloud sync)
- ✅ **Auto-start on boot** (systemd service)
- ✅ **Automatic updates** (daily at 2:00 AM)
- ✅ **Comitup WiFi hotspot** (web-based WiFi setup, no SSH needed)
- ✅ **addwifi.sh script** (backup WiFi configuration tool via SSH)
- ✅ **Tailscale remote access** (pre-installed, connect with auth key)
- ✅ **Camera support** (USB webcam)
- ✅ **Configuration management** (environment variables)
- ✅ **Debug frames disabled** (saves disk space, enable if needed)

---

## 🛠️ Prerequisites

### Hardware

- **Raspberry Pi 5** (4GB or 8GB RAM recommended)
- **MicroSD card** (32GB minimum, 64GB recommended)
- **USB webcam** (compatible with V4L2)
- **Power supply** (official Raspberry Pi 5 27W USB-C)
- **Internet connection** (Ethernet or WiFi)

### Software

- **Raspberry Pi OS Bookworm** (64-bit, Desktop or Lite)
- **SSH enabled** (via raspi-config or Imager settings)
- **VNC enabled** (optional, for remote desktop)

### Information Needed

Before starting, gather this information:

- ✅ **Cloud API URL** (your Railway/cloud deployment)
  - Example: `https://okmonitor-production.up.railway.app`
- ✅ **Device ID(s)** (unique identifier for each device)
  - Examples: `okmonitor1`, `floor-01-cam`, `warehouse-entrance`
- ✅ **WiFi credentials** (if using wireless)
  - SSID and password for each deployment site
- ✅ **Tailscale auth key** (optional, for remote access)
  - Generate at: https://login.tailscale.com/admin/settings/keys

---

## ⏱️ Time Estimates

### Route 1: Fresh Installation

| Task | Time |
|------|------|
| OS installation and boot | 10 min |
| Run install script | 15 min |
| Configuration and testing | 5 min |
| **Total per device** | **~30 min** |
| **10 devices** | **~5 hours** |

### Route 2: Golden Image Cloning

| Task | Time |
|------|------|
| Create golden image (one-time) | 45 min |
| Write image to SD card | 5 min |
| Boot and customize | 3 min |
| **Total per device** | **~8 min** |
| **10 devices** | **~1.5 hours** |

**Time savings for 10 devices: ~70%!**

---

## 🧪 Post-Deployment Verification

After deploying via either route, verify everything works:

```bash
# Run automated verification
sudo deployment/verify_deployment.sh
```

This checks:
- ✅ Service is running
- ✅ Camera is accessible
- ✅ Cloud API is reachable
- ✅ Configuration is valid
- ✅ Updates are scheduled
- ✅ All permissions are correct

📖 **See:** [verify_deployment.sh](verify_deployment.sh)

---

## 🌐 Additional Features

### 📱 WiFi Configuration

**Method 1: Comitup (Recommended for field deployment)** - No SSH needed!

Zero-touch WiFi setup:
1. Connect phone to **okmonitor-XXXX** WiFi (no password)
2. Open browser to **http://10.41.0.1**
3. Select customer WiFi and enter password
4. Device connects automatically!

📖 **Full guide:** [COMITUP.md](COMITUP.md)

**Method 2: addwifi.sh (Backup - requires SSH)**

Easy WiFi setup via command line:

```bash
~/addwifi.sh "Network-Name" "password" [priority]
```

📖 **Full guide:** [WIFI.md](WIFI.md)

### Remote Access (Tailscale)

Secure SSH and VNC access from anywhere:

```bash
sudo deployment/install_tailscale.sh --auth-key YOUR_KEY
```

📖 **Full guide:** [TAILSCALE.md](TAILSCALE.md)

### 🔄 Uninstall and Reinstall

Need to completely remove OK Monitor or perform a clean reinstall?

**Uninstall everything (preserves Tailscale for remote access):**

```bash
sudo deployment/uninstall.sh --keep-packages
```

**Safe remote reinstall (won't disconnect Tailscale):**

```bash
sudo deployment/install_device.sh --skip-tailscale
```

The uninstall script removes all OK Monitor components while intelligently preserving Tailscale, so you never lose remote access to your devices. Perfect for troubleshooting, upgrades, or clean reinstalls.

📖 **Full guide:** [UNINSTALL.md](UNINSTALL.md)

---

## 📚 Documentation Map

| Document | Purpose | Audience |
|----------|---------|----------|
| **README.md** (this file) | Overview and route selection | Everyone |
| [DEPLOYMENT.md](DEPLOYMENT.md) | Route 1 detailed guide | Installers |
| [CLONING.md](CLONING.md) | Route 2 detailed guide | Fleet managers |
| [QUICK-START-ROUTE1.md](QUICK-START-ROUTE1.md) | Route 1 cheat sheet | Field techs |
| [QUICK-START-ROUTE2.md](QUICK-START-ROUTE2.md) | Route 2 cheat sheet | Field techs |
| [COMITUP.md](COMITUP.md) | WiFi setup via web interface | On-site techs |
| [WIFI.md](WIFI.md) | WiFi configuration via SSH | Remote admins |
| [TAILSCALE.md](TAILSCALE.md) | Remote access setup | IT admins |
| [UNINSTALL.md](UNINSTALL.md) | Complete system removal | Admins |

---

## 🆘 Quick Troubleshooting

### Service won't start

```bash
sudo journalctl -u okmonitor-device -n 50
sudo systemctl status okmonitor-device
```

Common causes:
- Camera not connected → Check USB connection
- Wrong DEVICE_ID → Must not be "PLACEHOLDER_DEVICE_ID"
- API unreachable → Check network and API_URL

### Camera not found

```bash
v4l2-ctl --list-devices
ls -l /dev/video*
```

Solution: Update CAMERA_SOURCE in `/opt/okmonitor/.env.device`

### Network issues

```bash
curl -I https://okmonitor-production.up.railway.app/health
ping -c 4 8.8.8.8
```

Solution: Configure WiFi with `~/addwifi.sh` or connect Ethernet

### For detailed troubleshooting:
- Route 1 issues → See [DEPLOYMENT.md](DEPLOYMENT.md#troubleshooting)
- Route 2 issues → See [CLONING.md](CLONING.md#troubleshooting)

---

## 🚀 Quick Start Commands

### Route 1: Fresh Install
```bash
cd ~
git clone https://github.com/atxapple/okmonitor.git
cd okmonitor

# IMPORTANT: Configure .env.device FIRST
sudo mkdir -p /opt/okmonitor
sudo nano /opt/okmonitor/.env.device
# Set: API_URL, DEVICE_ID, CAMERA_SOURCE

# Then run installer with Tailscale (recommended)
sudo deployment/install_device.sh --tailscale-key tskey-auth-xxxxx
# Or without: sudo deployment/install_device.sh

sudo deployment/verify_deployment.sh  # Verify
```

### Reinstall (Remote - Preserves Tailscale)
```bash
# Uninstall (keeps Tailscale running)
sudo deployment/uninstall.sh --keep-packages

# Reinstall without touching Tailscale
sudo deployment/install_device.sh --skip-tailscale

sudo deployment/verify_deployment.sh  # Verify
```

### Route 2: Clone and Customize
```bash
# On each cloned device:
ssh mok@okmonitor.local
sudo deployment/customize_clone.sh  # Set device ID

# Configure WiFi - Method 1 (Comitup - no SSH needed):
# 1. Connect to okmonitor-XXXX WiFi
# 2. Browse to http://10.41.0.1
# 3. Configure customer WiFi

# Or Method 2 (addwifi.sh via SSH):
~/addwifi.sh "WiFi-Name" "password"

sudo deployment/verify_deployment.sh  # Verify
```

---

## 💡 Best Practices

### Naming Convention

Use descriptive, consistent device IDs:

**Good:**
- `floor-01-cam` - Clear location
- `warehouse-entrance` - Clear purpose
- `site-alpha-cam-01` - Site + sequence

**Bad:**
- `cam1` - Too generic
- `test` - Not descriptive
- `raspberry-pi` - Doesn't indicate purpose

### Security

1. **Change default password:**
   ```bash
   passwd
   ```

2. **Enable Tailscale** for secure remote access instead of opening ports

3. **Don't commit credentials** to git repository

4. **Use strong WiFi passwords** (12+ characters)

### Maintenance

- Updates happen automatically at 2:00 AM daily
- Monitor logs: `sudo journalctl -u okmonitor-device -f`
- Check update logs: `sudo cat /var/log/okmonitor-update.log`
- For fleet updates, use Tailscale + SSH for bulk operations

---

## 📞 Support

### Common Issues

Most issues are covered in:
- [DEPLOYMENT.md - Troubleshooting](DEPLOYMENT.md#troubleshooting)
- [CLONING.md - Troubleshooting](CLONING.md#troubleshooting)

### Getting Help

1. **Check logs:** `sudo journalctl -u okmonitor-device -f`
2. **Run verification:** `sudo deployment/verify_deployment.sh`
3. **Review documentation** for your route
4. **Check GitHub issues:** https://github.com/atxapple/okmonitor/issues
5. **Contact support** with logs and error messages

---

## 📊 Deployment Comparison

|  | Route 1: Fresh Install | Route 2: Golden Image |
|---|---|---|
| **Setup time** | 30 min/device | 5 min/device |
| **Internet needed** | Yes | No (after image created) |
| **Consistency** | Good | Excellent |
| **Flexibility** | High | Medium |
| **Ideal for** | 1-5 devices | 10+ devices |
| **Difficulty** | Medium | Easy |
| **Updates** | Automatic (git pull) | Automatic (git pull) |
| **Customization** | During install | After clone |

---

## 🎓 Learning Path

**New to OK Monitor?** Follow this path:

1. **Read this README** - Understand both routes
2. **Try Route 1 on one device** - Learn the system
3. **Read DEPLOYMENT.md** - Understand all features
4. **Deploy Route 1 to 2-3 devices** - Gain experience
5. **When ready for fleet, use Route 2** - Scale efficiently

**For field technicians:**
- Print [QUICK-START-ROUTE1.md](QUICK-START-ROUTE1.md) or [QUICK-START-ROUTE2.md](QUICK-START-ROUTE2.md)
- Laminate for durability
- Keep with deployment kit

---

## ✅ Deployment Checklist

Print this checklist for each deployment:

```
Hardware Setup:
□ Raspberry Pi 5 with power supply
□ MicroSD card inserted (32GB+)
□ USB webcam connected
□ Ethernet cable or WiFi credentials available

Pre-Deployment:
□ Raspberry Pi OS installed (Bookworm 64-bit)
□ SSH enabled
□ Device booted and accessible
□ Cloud API URL confirmed
□ Device ID chosen (unique)

Route 1 Installation:
□ Repository cloned
□ install_device.sh executed
□ .env.device configured
□ Service started successfully

Route 2 Cloning:
□ Golden image written to SD card
□ Device booted
□ customize_clone.sh executed
□ Unique device ID set

Post-Deployment:
□ verify_deployment.sh passed all checks
□ Camera captures working
□ Cloud connectivity confirmed
□ WiFi configured (if needed)
□ Tailscale connected (if needed)
□ Device ID labeled on hardware

Acceptance:
□ Service runs for 10+ minutes without errors
□ Captures uploading to cloud
□ Auto-start verified (reboot test)
□ Documentation handed off
```

---

## 🔄 Version History

- **v1.0** - Initial deployment system
  - Fresh installation script
  - Golden image cloning
  - WiFi and Tailscale support
  - Automatic updates
  - Comprehensive documentation

---

**Ready to deploy?** Choose your route above and get started! 🚀
