# On-Site Installation Guide - Mobile Hotspot Method

**Quick deployment for field technicians using mobile hotspot**

---

## Overview

This guide covers the recommended on-site installation workflow where you:
1. ✅ Use your phone's mobile hotspot for initial access
2. ✅ SSH to device from your phone
3. ✅ Configure customer WiFi using `addwifi.sh`
4. ✅ Device automatically switches to customer network

**No monitor, keyboard, or Ethernet cable needed!**

---

## Prerequisites

### What You Need
- ☐ Mobile phone with hotspot capability
- ☐ SSH client app on your phone
  - **Android**: Termius, JuiceSSH, ConnectBot
  - **iOS**: Termius, Prompt
- ☐ Raspberry Pi device (with golden image or fresh installation)
- ☐ Customer WiFi credentials (SSID and password)

### What's Pre-Configured
- ✅ Device automatically connects to hotspot SSID: **okadmin**
- ✅ Hotspot password: **00000002**
- ✅ All cloned devices have this pre-configured

---

## Quick Setup (5 Minutes)

### Step 1: Enable Mobile Hotspot

**On your phone:**
1. Open Settings → Mobile Hotspot (or Personal Hotspot)
2. Configure hotspot:
   - **SSID**: `okadmin`
   - **Password**: `00000002`
   - **Band**: 2.4GHz (recommended - better range)
3. Enable hotspot

**Android Example:**
```
Settings → Connections → Mobile Hotspot and Tethering
→ Mobile Hotspot → Configure
   Network name: okadmin
   Password: 00000002
   Band: 2.4GHz
→ Turn ON
```

**iOS Example:**
```
Settings → Personal Hotspot
→ Wi-Fi Password: 00000002
   (Note: iOS uses device name as SSID - may need to rename device to "okadmin")
→ Allow Others to Join: ON
```

☐ Mobile hotspot enabled

---

### Step 2: Power On Raspberry Pi

1. Insert SD card (if not already inserted)
2. Connect USB camera
3. Connect power supply
4. Wait **60 seconds** for boot and auto-connect

**What happens:**
- Device boots up
- Automatically scans for WiFi networks
- Connects to "okadmin" hotspot (pre-configured)
- Gets IP address from your phone

☐ Device powered on and booted

---

### Step 3: Find Device IP Address

**On your phone:**

**Android:**
```
Settings → Connections → Mobile Hotspot and Tethering
→ Mobile Hotspot → Connected devices
→ Look for "okmonitor" or "raspberrypi"
→ Note the IP address (e.g., 192.168.43.123)
```

**iOS:**
```
Settings → Personal Hotspot
→ Connected devices shows number
→ Need to check DHCP leases or use network scanner app
→ Common range: 172.20.10.2 - 172.20.10.15
```

**Common IP Ranges:**
- Android hotspot: `192.168.43.xxx`
- iOS hotspot: `172.20.10.xxx`
- Some phones: `192.168.137.xxx`

**Pro Tip:** Use a network scanner app:
- **Android**: Fing, Network Scanner
- **iOS**: Fing, iNet

☐ Device IP address found: _______________

---

### Step 4: SSH to Device

Open your SSH client app and connect:

```
Host: 192.168.43.123  (use your device's IP)
Username: mok
Password: [your device password]
Port: 22
```

**First time connecting:**
- You'll see SSH key fingerprint warning
- Accept and continue

**Expected:**
```
mok@okmonitor:~ $
```

☐ SSH connection established

---

### Step 5: Configure Customer WiFi

Run the WiFi configuration script:

```bash
~/addwifi.sh "Customer-WiFi-Name" "customer-password" 200
```

**Example:**
```bash
~/addwifi.sh "Starbucks-Guest" "coffee123" 200
```

**What the script does:**
1. Creates WiFi profile for customer network
2. Sets priority to 200 (higher than okadmin's 50)
3. Enables auto-connect
4. Activates the connection

**Expected output:**
```
===== WiFi Configuration =====

Network:  Customer-WiFi-Name
Priority: 200

WiFi interface: wlan0

Creating new profile 'Customer-WiFi-Name'…
Configuring security…
Setting priority and autoconnect…
Activating connection…

===== Success! =====
Connected to: Customer-WiFi-Name
IP Address: 192.168.1.45/24
Gateway:    192.168.1.1

The network will automatically connect on boot.
```

☐ Customer WiFi configured

---

### Step 6: Device Switches Networks

**What happens automatically:**

1. Device connects to customer WiFi (priority 200)
2. Device disconnects from okadmin hotspot (priority 50)
3. Your SSH session will disconnect
4. Device is now on customer network

**This is expected and normal!**

☐ Device switched to customer WiFi

---

### Step 7: Verify via Tailscale

Since device is now on customer network (different from your phone), use Tailscale for verification:

```bash
# On your phone SSH client, connect via Tailscale
ssh mok@okmonitor-olivia  # Use your device's Tailscale hostname

# Or use Tailscale IP
ssh mok@100.101.102.103
```

**Verify device is working:**
```bash
# Check WiFi connection
nmcli connection show --active

# Check device service
sudo systemctl status okmonitor-device

# Check camera
v4l2-ctl --list-devices
```

☐ Device verified via Tailscale

---

## Complete Workflow Summary

```
┌─────────────────────────────────────────────────┐
│  1. Enable phone hotspot: okadmin / 00000002    │
└─────────────────────────────────────────────────┘
                     ↓
┌─────────────────────────────────────────────────┐
│  2. Power on Raspberry Pi (auto-connects)       │
└─────────────────────────────────────────────────┘
                     ↓
┌─────────────────────────────────────────────────┐
│  3. Find device IP in hotspot settings          │
└─────────────────────────────────────────────────┘
                     ↓
┌─────────────────────────────────────────────────┐
│  4. SSH from phone: mok@192.168.43.xxx          │
└─────────────────────────────────────────────────┘
                     ↓
┌─────────────────────────────────────────────────┐
│  5. Run: ~/addwifi.sh "Customer" "pass" 200     │
└─────────────────────────────────────────────────┘
                     ↓
┌─────────────────────────────────────────────────┐
│  6. Device switches to customer WiFi            │
│     (SSH session disconnects - this is normal)  │
└─────────────────────────────────────────────────┘
                     ↓
┌─────────────────────────────────────────────────┐
│  7. Verify via Tailscale: ssh mok@okmonitor-... │
└─────────────────────────────────────────────────┘
```

**Total time: ~5 minutes**

---

## Troubleshooting

### Device Not Connecting to okadmin Hotspot

**Symptoms:** Device doesn't appear in hotspot's connected devices list

**Possible causes:**

1. **Hotspot name is wrong**
   - Must be exactly: `okadmin` (case-sensitive)
   - Check your hotspot SSID

2. **Password is wrong**
   - Must be exactly: `00000002` (8 zeros, then a 2)
   - Check your hotspot password

3. **Wrong WiFi band**
   - Use 2.4GHz (not 5GHz)
   - Raspberry Pi built-in WiFi prefers 2.4GHz
   - Better range for on-site installations

4. **Device hasn't booted yet**
   - Wait full 60 seconds after power on
   - First boot takes longer

5. **okadmin profile not configured (golden image issue)**
   - Device needs okadmin pre-configured or added manually
   - See "Manual okadmin Setup" below

**Solution:**
```bash
# If you can access device via Ethernet or different network:
ssh mok@raspberrypi.local
~/addwifi.sh "okadmin" "00000002" 50
```

---

### Can't Find Device IP Address

**Symptoms:** Device connected but can't find IP

**Solutions:**

1. **Check all connected devices:**
   - Look for "okmonitor", "raspberrypi", or "Unknown"
   - Note ALL IPs in range and try each

2. **Use network scanner app:**
   - Install Fing or Network Scanner
   - Scan hotspot network
   - Look for Raspberry Pi devices (vendor: Raspberry Pi Foundation)

3. **Try common IP addresses:**
   ```bash
   # Android hotspot range
   ssh mok@192.168.43.1
   ssh mok@192.168.43.2
   ssh mok@192.168.43.100

   # iOS hotspot range
   ssh mok@172.20.10.2
   ssh mok@172.20.10.3
   ```

4. **Check hotspot DHCP range:**
   - Some phones limit DHCP range
   - Expand range in hotspot settings if available

---

### Customer WiFi Not Working

**Symptoms:** addwifi.sh runs but connection fails

**Common issues:**

1. **Wrong password:**
   ```bash
   # Try again with correct password
   ~/addwifi.sh "Customer-WiFi" "correct-password" 200
   ```

2. **Hidden network:**
   ```bash
   # Add --hidden flag
   ~/addwifi.sh "Hidden-Network" "password" 200 --hidden
   ```

3. **WiFi out of range:**
   - Move device closer to customer access point
   - Check signal strength:
     ```bash
     nmcli device wifi list
     # Look for SIGNAL column (should be >50)
     ```

4. **Network requires special authentication:**
   - Some corporate networks use WPA2-Enterprise
   - May need manual configuration
   - See WIFI.md for advanced setup

---

### SSH Session Keeps Disconnecting

**Symptoms:** SSH drops during configuration

**Causes:**
- Phone hotspot power-saving mode
- Weak cellular signal
- Phone receiving call

**Solutions:**
1. **Disable power saving on hotspot:**
   - Keep phone plugged in during setup
   - Disable battery optimization for hotspot

2. **Use stable location:**
   - Good cellular signal
   - Away from interference

3. **Work quickly:**
   - Have customer WiFi credentials ready
   - Copy-paste commands when possible

---

### Device Won't Switch to Customer WiFi

**Symptoms:** Device stays on okadmin after running addwifi.sh

**Check:**
```bash
# List all WiFi connections with priorities
nmcli -t -f NAME,AUTOCONNECT-PRIORITY connection show | grep -v ethernet

# Should see:
# Customer-WiFi:200
# okadmin:50
```

**If priorities are wrong:**
```bash
# Manually set priority
sudo nmcli connection modify "Customer-WiFi" connection.autoconnect-priority 200
sudo nmcli connection modify "okadmin" connection.autoconnect-priority 50

# Reconnect
sudo nmcli connection up "Customer-WiFi"
```

---

## Advanced: Manual okadmin Setup

If your golden image doesn't have okadmin pre-configured:

### On Device (via Ethernet or other WiFi):

```bash
# Add okadmin hotspot profile
~/addwifi.sh "okadmin" "00000002" 50

# Verify
~/addwifi.sh --list
```

### In Golden Image Preparation:

```bash
# Before creating golden image
sudo nmcli connection add type wifi ifname wlan0 \
    con-name okadmin ssid okadmin \
    wifi-sec.key-mgmt wpa-psk \
    wifi-sec.psk "00000002" \
    connection.autoconnect yes \
    connection.autoconnect-priority 50

# Then proceed with prepare_for_clone.sh
```

---

## Tips & Best Practices

### For Technicians

1. **Pre-setup checklist:**
   - ☐ Hotspot configured (okadmin / 00000002)
   - ☐ SSH client installed on phone
   - ☐ Customer WiFi credentials in notes app
   - ☐ Tailscale installed on phone (for verification)

2. **Save common commands:**
   - Save addwifi.sh command template in notes
   - Just change SSID and password for each site

3. **Test hotspot first:**
   - Connect your laptop to okadmin hotspot
   - Verify it works before going on-site

4. **Keep customer informed:**
   - "I'm configuring the device to your WiFi"
   - "This will take about 5 minutes"
   - "The device needs to restart - that's normal"

### For Fleet Managers

1. **Standardize credentials:**
   - All technicians use same okadmin hotspot
   - Easier to troubleshoot and support

2. **Golden image includes okadmin:**
   - Pre-configure in golden image
   - Every cloned device auto-connects

3. **Document site-specific details:**
   - Customer WiFi SSID
   - Device ID used
   - Tailscale hostname
   - Installation date and technician

4. **Provide mobile SSH training:**
   - Train technicians on mobile SSH apps
   - Practice on demo device before field deployment

---

## Why This Method Works

### Benefits

1. **No Extra Equipment:**
   - No monitor needed
   - No keyboard needed
   - No Ethernet cable needed
   - Technician only needs their phone

2. **Fast Deployment:**
   - 5 minutes from power-on to configured
   - No need to wait for customer IT
   - Works even if customer WiFi isn't ready yet

3. **Flexible:**
   - Can configure device anywhere
   - Can reconfigure if customer changes WiFi
   - Can access device from anywhere (via hotspot or Tailscale)

4. **Consistent:**
   - Same process for every installation
   - Standardized credentials (okadmin)
   - Predictable behavior

### How It Works

1. **Priority-based WiFi:**
   - okadmin hotspot: priority 50 (low)
   - Customer WiFi: priority 200 (high)
   - Device always prefers higher priority

2. **Auto-connect:**
   - Device remembers both networks
   - Connects to highest-priority available network
   - Seamlessly switches when both are in range

3. **Temporary access:**
   - okadmin is only used during setup
   - Device uses customer WiFi for production
   - okadmin still available for future maintenance

---

## Integration with Other Guides

- **Full WiFi guide:** [WIFI.md](WIFI.md)
- **Fresh installation:** [QUICK-START-ROUTE1.md](QUICK-START-ROUTE1.md)
- **Clone deployment:** [QUICK-START-ROUTE2.md](QUICK-START-ROUTE2.md)
- **Remote access:** [TAILSCALE.md](TAILSCALE.md)
- **Main deployment guide:** [README.md](README.md)

---

## Support

**Issue during on-site setup?**

1. Check this troubleshooting guide first
2. Verify hotspot settings (okadmin / 00000002)
3. Try Ethernet connection as backup
4. Contact support with:
   - Device ID
   - Error messages (take screenshots)
   - Customer WiFi details (SSID, security type)

---

**Happy deploying! 📱→🔧→✅**
