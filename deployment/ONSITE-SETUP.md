# On-Site Installation Guide - Comitup WiFi Setup

**Quick deployment for field technicians using Comitup web interface**

---

## Overview

This guide covers the recommended on-site installation workflow using Comitup:
1. ✅ Connect phone/laptop to device's WiFi hotspot (no password)
2. ✅ Open web browser to configure WiFi
3. ✅ Select customer WiFi network
4. ✅ Device automatically connects to customer network

**No monitor, keyboard, SSH, or Ethernet cable needed!**

---

## Prerequisites

### What You Need
- ☐ Mobile phone or laptop with WiFi
- ☐ Web browser (any modern browser)
- ☐ Raspberry Pi device with Comitup installed
- ☐ Customer WiFi credentials (SSID and password)

### What's Pre-Configured
- ✅ Comitup automatically installed during device setup
- ✅ Device creates open WiFi hotspot: **okmonitor-XXXX** (no password)
- ✅ Web interface available at: **http://10.41.0.1**
- ✅ Automatic fallback to hotspot if WiFi fails

---

## Quick Setup (3 Minutes)

### Step 1: Power On Raspberry Pi

1. Insert SD card (if not already inserted)
2. Connect USB camera
3. Connect power supply
4. Wait **60 seconds** for boot

**What happens:**
- Device boots up
- No WiFi configured → Comitup starts automatically
- Device creates WiFi hotspot: **okmonitor-XXXX**
- Web interface ready at **http://10.41.0.1**

☐ Device powered on and booted

---

### Step 2: Connect to Device Hotspot

**On your phone or laptop:**

1. Open WiFi settings
2. Scan for available networks
3. Look for network named: **okmonitor-XXXX** (e.g., `okmonitor-1a2b`)
4. Connect to this network
   - **Password**: None (open network)

**What happens:**
- Your device connects to the Raspberry Pi's hotspot
- You may see "No internet connection" warning - this is normal
- Your browser may automatically open the configuration page

☐ Connected to okmonitor-XXXX WiFi

---

### Step 3: Open Configuration Page

**On your phone/laptop:**

1. Open web browser (Chrome, Safari, Firefox, etc.)
2. Navigate to: **http://10.41.0.1**
3. You'll see the Comitup web interface

**What you'll see:**
- List of available WiFi networks
- Signal strength for each network
- Connection status

☐ Configuration page opened

---

### Step 4: Configure Customer WiFi

**In the web interface:**

1. **Find customer's WiFi** in the list of available networks
2. **Click on the network name**
3. **Enter WiFi password** when prompted
4. **Click "Connect"**

**What happens:**
- Device attempts to connect to customer WiFi
- May take 30-60 seconds
- Your phone/laptop will disconnect from hotspot
- Device is now connected to customer network!

☐ Customer WiFi configured

---

### Step 5: Verify Connection

**Option 1: Via cloud dashboard**
- Check your OK Monitor dashboard
- Device should appear online with its DEVICE_ID
- Captures should start uploading

**Option 2: Via SSH (if Tailscale configured)**
```bash
ssh mok@okmonitor-<device-id>
# Check service status
sudo systemctl status okmonitor-device
```

☐ Deployment verified

---

## Troubleshooting

### Can't Find okmonitor-XXXX WiFi Network

**Check device is powered on:**
- Power LED should be lit
- Wait at least 60 seconds after power on

**Check WiFi is enabled on your phone/laptop:**
- Toggle WiFi off and on
- Scan for networks again

**Restart device:**
```bash
# If you have SSH access
sudo reboot

# Otherwise, power cycle
# Unplug power → Wait 10 seconds → Plug back in
```

---

### Can't Access http://10.41.0.1

**Verify you're connected to okmonitor-XXXX:**
- Check WiFi status on your device
- Should show "Connected" (may say "No internet")

**Try these URLs:**
- http://10.41.0.1
- http://10.41.0.1:80
- http://comitup.local

**Clear browser cache:**
- Try incognito/private browsing
- Try different browser

---

### WiFi Password Incorrect

**Check password carefully:**
- Passwords are case-sensitive
- Check for special characters
- Ask customer to verify

**Try again:**
- Re-select network in Comitup interface
- Re-enter password carefully
- Click "Connect"

---

### Connection Failed - Returns to Hotspot

**Check WiFi signal:**
- Move Raspberry Pi closer to router
- Check signal bars in Comitup interface

**Verify network settings:**
- Ensure WiFi router is working
- Check if network requires additional auth (captive portal)
- Try different WiFi network if available

**Check router compatibility:**
- Some enterprise WiFi won't work (WPA2-Enterprise)
- Guest networks usually work better
- 2.4GHz band preferred over 5GHz

---

## Alternative: SSH Method (Backup)

If Comitup web interface isn't accessible, use SSH method:

### Requirements
- SSH access to device (Ethernet or Tailscale)
- Terminal/SSH client

### Steps

1. **Connect via SSH:**
```bash
ssh mok@okmonitor.local
# or via Tailscale
ssh mok@okmonitor-<device-id>
```

2. **Configure WiFi:**
```bash
~/addwifi.sh "Customer-WiFi" "password" 200
```

3. **Verify:**
```bash
nmcli device status
ping -c 3 8.8.8.8
```

📖 **Full SSH method guide:** [WIFI.md](WIFI.md)

---

## Tips for Field Technicians

### Before Leaving Site

✅ Checklist:
- ☐ Device connected to customer WiFi
- ☐ Green LED indicates network activity
- ☐ Device appears online in dashboard
- ☐ Captures uploading successfully
- ☐ Camera positioned correctly
- ☐ Power cable secured
- ☐ Device ID label applied

### Common Site Issues

**Weak WiFi signal:**
- Relocate device closer to router
- Use WiFi extender if needed
- Consider Ethernet cable

**Hidden network:**
- Customer must provide exact SSID
- Use SSH method instead of Comitup

**Multiple locations:**
- Configure both WiFi networks
- Device auto-switches based on signal

---

## Advanced Scenarios

### Multiple WiFi Networks

Comitup can save multiple networks:

1. Configure first network (office)
2. Later, at different site, hotspot appears again
3. Configure second network (warehouse)
4. Device remembers both, auto-connects to whichever is in range

### Changing WiFi Password

If customer changes WiFi password:

1. Device loses connection
2. Automatically reverts to hotspot mode
3. Connect to okmonitor-XXXX again
4. Reconfigure with new password

### Removing Old Networks

Via SSH:
```bash
# List all saved networks
nmcli connection show

# Delete specific network
sudo nmcli connection delete "Old-Network-Name"
```

---

## For More Information

### Detailed Comitup Documentation
📖 [COMITUP.md](COMITUP.md) - Complete Comitup guide

### Alternative WiFi Methods
📖 [WIFI.md](WIFI.md) - SSH-based WiFi configuration

### Remote Access
📖 [TAILSCALE.md](TAILSCALE.md) - Remote SSH/VNC access

### Full Deployment Guide
📖 [DEPLOYMENT.md](DEPLOYMENT.md) - Complete installation guide

---

## Quick Reference Card

**Print this section for field techs:**

```
╔═══════════════════════════════════════════════════════╗
║           OK Monitor On-Site Setup - Comitup           ║
╠═══════════════════════════════════════════════════════╣
║                                                        ║
║  1. Power on Raspberry Pi → Wait 60 seconds           ║
║                                                        ║
║  2. Connect to WiFi: okmonitor-XXXX (no password)     ║
║                                                        ║
║  3. Open browser: http://10.41.0.1                    ║
║                                                        ║
║  4. Click customer WiFi → Enter password → Connect    ║
║                                                        ║
║  5. Verify in dashboard → Done!                       ║
║                                                        ║
╠═══════════════════════════════════════════════════════╣
║  Troubleshooting:                                     ║
║  • No hotspot? Power cycle and wait 60 sec            ║
║  • Can't access web? Try http://comitup.local         ║
║  • Connection failed? Check signal strength           ║
╚═══════════════════════════════════════════════════════╝
```

---

**Deployment complete!** ✅
