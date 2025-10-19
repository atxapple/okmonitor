# WiFi Configuration for OK Monitor Devices

This guide covers WiFi network configuration for Raspberry Pi devices running OK Monitor.

---

## 📱 On-Site Installation (Recommended Method)

**For field technicians:** Use mobile hotspot for initial setup without monitor/keyboard!

### Quick Setup (5 Minutes)

1. Enable mobile hotspot on your phone:
   - **SSID**: `okadmin`
   - **Password**: `00000002`
2. Power on Raspberry Pi (auto-connects to okadmin)
3. SSH from phone: `ssh mok@192.168.43.xxx`
4. Configure customer WiFi: `~/addwifi.sh "Customer-WiFi" "password" 200`
5. Device automatically switches to customer network

**📖 Complete guide:** [ONSITE-SETUP.md](ONSITE-SETUP.md)

**Why this works:**
- ✅ No monitor/keyboard needed
- ✅ Cloned devices include okadmin pre-configured
- ✅ Priority-based: customer WiFi (200) > okadmin (50)
- ✅ Deploy from anywhere with just your phone

---

## Quick Start

The `addwifi.sh` script is automatically installed to your home directory during device setup.

### Basic Usage

```bash
# Add a WiFi network
~/addwifi.sh "Network-Name" "password123"

# List all saved networks
~/addwifi.sh --list

# Show help
~/addwifi.sh --help
```

---

## Common Scenarios

### Scenario 1: New Installation Site

You've just installed a Raspberry Pi at a customer location and need to connect it to their WiFi:

```bash
# Connect to customer WiFi
~/addwifi.sh "CustomerWiFi" "their-password"

# Verify connection
ip addr show wlan0
ping -c 3 8.8.8.8
```

### Scenario 2: Multiple Network Locations

Device moves between office, warehouse, and backup locations:

```bash
# Office network (highest priority)
~/addwifi.sh "Office-WiFi" "office-pass" 200

# Warehouse network (medium priority)
~/addwifi.sh "Warehouse-WiFi" "warehouse-pass" 150

# Backup hotspot (lowest priority)
~/addwifi.sh "Mobile-Hotspot" "hotspot-pass" 50

# Check all configured networks
~/addwifi.sh --list
```

**Result:** Device will automatically connect to the highest-priority available network.

### Scenario 3: Hidden Network

Some secure installations use hidden SSIDs:

```bash
# Add hidden network
~/addwifi.sh "Hidden-Secure-Net" "secret-password" 100 --hidden
```

### Scenario 4: Temporary Access Point

During initial setup or troubleshooting:

```bash
# Connect to temporary phone hotspot
~/addwifi.sh "iPhone-Hotspot" "temp-pass" 10

# Later, check all networks
~/addwifi.sh --list
```

---

## Understanding Priority

Priority values range from 0-999. Higher numbers connect first when multiple networks are in range.

### Recommended Priority Scheme

| Location Type | Priority | Use Case |
|--------------|----------|----------|
| Primary Site | 200 | Main production location |
| Secondary Site | 150 | Backup or alternate location |
| Office/Admin | 100 | Administrative access |
| **okadmin Hotspot** | **50** | **On-site installation (pre-configured)** |
| Mobile Hotspot | 50 | Emergency connectivity |
| Guest/Temp | 10 | Temporary access |

### Example: Multi-Site Deployment

```bash
# Factory floor (primary)
~/addwifi.sh "Factory-Production" "prod-pass" 200

# Office area (secondary)
~/addwifi.sh "Factory-Office" "office-pass" 150

# Manager's mobile hotspot (emergency)
~/addwifi.sh "Manager-Phone" "hotspot-pass" 50
```

When the device is on the factory floor, it connects to "Factory-Production". If that network goes down, it automatically fails over to "Factory-Office", then to the mobile hotspot if needed.

---

## Network Management

### List All Saved Networks

```bash
~/addwifi.sh --list
```

Output example:
```
===== Saved WiFi Profiles =====

Office-WiFi                    Priority: 200   Auto-connect: yes
Warehouse-WiFi                 Priority: 150   Auto-connect: yes
Mobile-Hotspot                 Priority: 50    Auto-connect: yes

Active connection:
  Office-WiFi (on wlan0)
```

### Update Existing Network

Simply run the same command again with updated values:

```bash
# Change password
~/addwifi.sh "Office-WiFi" "new-password-2024" 200

# Change priority
~/addwifi.sh "Office-WiFi" "same-password" 250
```

### Remove a Network

Use NetworkManager directly:

```bash
# List connections
nmcli connection show

# Delete a connection
sudo nmcli connection delete "Network-Name"
```

### Check Current Connection

```bash
# Show active WiFi connection
nmcli connection show --active | grep wifi

# Show signal strength and details
nmcli device wifi list
```

---

## Troubleshooting

### WiFi Not Connecting

**Check if WiFi hardware is enabled:**
```bash
nmcli radio wifi on
nmcli device status
```

**Check network is in range:**
```bash
sudo nmcli device wifi list
# Look for your SSID in the list
```

**Test connection manually:**
```bash
sudo nmcli connection up "Network-Name"
```

**Check logs:**
```bash
sudo journalctl -u NetworkManager -n 50
```

### Wrong Password

If you entered the wrong password, simply re-run with the correct one:

```bash
~/addwifi.sh "Network-Name" "correct-password"
```

### Network Keeps Disconnecting

**Check signal strength:**
```bash
nmcli device wifi list
# Signal column shows strength (0-100)
# Aim for >50 for stable connection
```

**If signal is weak:**
- Reposition the Raspberry Pi closer to the access point
- Check for physical obstructions (metal cabinets, thick walls)
- Consider adding a WiFi USB adapter with external antenna
- Add a network extender/repeater

**Check for interference:**
```bash
# Scan for nearby networks on same channel
sudo iwlist wlan0 scan | grep -E "ESSID|Channel|Quality"
```

### Auto-Connect Not Working After Reboot

**Verify auto-connect is enabled:**
```bash
nmcli connection show "Network-Name" | grep autoconnect
```

**If disabled, enable it:**
```bash
sudo nmcli connection modify "Network-Name" connection.autoconnect yes
```

**Check boot order:**
```bash
# Ensure NetworkManager starts before okmonitor-device
systemctl list-dependencies okmonitor-device.service
```

### Multiple Devices Connecting to Wrong Network

This happens when all networks have the same priority.

**Solution:** Differentiate priorities:
```bash
~/addwifi.sh "Preferred-Network" "pass1" 200
~/addwifi.sh "Backup-Network" "pass2" 100
```

### Hidden Network Not Found

**Verify SSID is typed exactly:**
```bash
# SSID is case-sensitive!
# "MyNetwork" ≠ "mynetwork" ≠ "MYNETWORK"
```

**Check network is actually hidden:**
```bash
# If you see it in this list, don't use --hidden flag
sudo nmcli device wifi list
```

### Can't Find WiFi Interface

**Check WiFi hardware:**
```bash
# List all network devices
nmcli device status

# Check for WiFi driver
lsusb  # For USB WiFi adapters
dmesg | grep -i wifi
```

**If no interface found:**
- Check physical connection (USB WiFi adapter)
- Verify driver is installed
- Check if WiFi is disabled in BIOS/firmware

---

## Advanced Usage

### Using Specific WiFi Interface

If you have multiple WiFi adapters:

```bash
# List interfaces
nmcli device status | grep wifi

# The script auto-selects, but you can manually create:
sudo nmcli connection add type wifi ifname wlan1 con-name "MyNet" ssid "MyNet"
sudo nmcli connection modify "MyNet" wifi-sec.key-mgmt wpa-psk wifi-sec.psk "password"
```

### Static IP Configuration

For devices requiring fixed IP addresses:

```bash
# First, add the network normally
~/addwifi.sh "Static-Network" "password" 200

# Then configure static IP
sudo nmcli connection modify "Static-Network" \
    ipv4.method manual \
    ipv4.addresses 192.168.1.100/24 \
    ipv4.gateway 192.168.1.1 \
    ipv4.dns "8.8.8.8 8.8.4.4"

# Bring connection up
sudo nmcli connection up "Static-Network"
```

### Enterprise WiFi (WPA2-Enterprise)

For networks requiring username/password authentication:

```bash
# Create connection
sudo nmcli connection add type wifi ifname wlan0 con-name "Enterprise-WiFi" ssid "Enterprise-WiFi"

# Configure WPA2-Enterprise
sudo nmcli connection modify "Enterprise-WiFi" \
    wifi-sec.key-mgmt wpa-eap \
    802-1x.eap peap \
    802-1x.phase2-auth mschapv2 \
    802-1x.identity "username" \
    802-1x.password "password"

# Activate
sudo nmcli connection up "Enterprise-WiFi"
```

### Custom MAC Address

To use a specific MAC address:

```bash
~/addwifi.sh "Network-Name" "password"

# Then set custom MAC
sudo nmcli connection modify "Network-Name" \
    802-11-wireless.cloned-mac-address "AA:BB:CC:DD:EE:FF"

sudo nmcli connection up "Network-Name"
```

---

## Integration with OK Monitor

### Installation

The WiFi script is automatically installed during device setup:

```bash
# Already done by install_device.sh:
# - Copied to /home/{user}/addwifi.sh
# - Made executable
# - User ownership set
```

### During Device Installation

1. Run device installer:
   ```bash
   sudo deployment/install_device.sh
   ```

2. Configure WiFi (if needed):
   ```bash
   ~/addwifi.sh "Site-WiFi" "password"
   ```

3. Continue with device configuration:
   ```bash
   sudo nano /opt/okmonitor/.env.device
   ```

### Remote WiFi Configuration via Tailscale

Once Tailscale is set up, you can configure WiFi remotely:

```bash
# From your laptop (connected to Tailscale)
ssh mok@okmonitor-okmonitor1

# On the device
~/addwifi.sh "New-Site-WiFi" "new-password" 200
```

### Bulk Fleet WiFi Configuration

For multiple devices at the same location:

```bash
#!/bin/bash
# deploy_wifi_to_fleet.sh

NETWORK="Factory-WiFi"
PASSWORD="factory-pass-2024"
DEVICES=("okmonitor-okmonitor1" "okmonitor-okmonitor2" "okmonitor-okmonitor3")

for device in "${DEVICES[@]}"; do
    echo "Configuring WiFi on $device..."
    ssh mok@$device "~/addwifi.sh '$NETWORK' '$PASSWORD' 200"
done
```

Run from your management machine:
```bash
chmod +x deploy_wifi_to_fleet.sh
./deploy_wifi_to_fleet.sh
```

---

## Security Best Practices

### Password Management

1. **Use strong passwords:**
   - Minimum 12 characters
   - Mix of uppercase, lowercase, numbers, symbols
   - Avoid common words or patterns

2. **Don't store passwords in plain text:**
   - The script requires the password as input
   - Never commit passwords to git
   - Use password managers for organization

3. **Rotate passwords regularly:**
   - Update network passwords every 90 days
   - Use the update command to change credentials:
     ```bash
     ~/addwifi.sh "Network-Name" "new-password-2024" 200
     ```

### Network Security

1. **Prefer WPA2/WPA3:**
   - Avoid WEP or open networks
   - The script uses WPA2-PSK by default

2. **Use hidden networks when possible:**
   - Adds a layer of obscurity
   - Remember to use `--hidden` flag

3. **Separate device networks:**
   - Consider IoT-specific network segment
   - Isolate monitoring devices from corporate network

### Physical Security

1. **Protect device access:**
   - Keep Raspberry Pi in locked enclosure
   - Limit physical access to trusted personnel

2. **Secure credentials:**
   - Don't leave passwords written near devices
   - Train technicians on secure password handling

---

## Monitoring WiFi Health

### Check Connection Status

Add to your monitoring dashboard:

```bash
# Check if connected
nmcli -t -f DEVICE,STATE device | grep wlan0

# Get signal strength
nmcli -t -f IN-USE,SIGNAL,SSID device wifi | grep "^*"

# Get IP address
ip -4 addr show wlan0 | grep -oP '(?<=inet\s)\d+(\.\d+){3}'
```

### Log WiFi Events

Monitor NetworkManager logs:

```bash
# Watch for connection changes
sudo journalctl -u NetworkManager -f

# Filter for specific network
sudo journalctl -u NetworkManager | grep "Network-Name"
```

### Alert on Disconnection

Create a simple monitor script:

```bash
#!/bin/bash
# wifi_monitor.sh

while true; do
    if ! nmcli -t -f DEVICE,STATE device | grep -q "wlan0:connected"; then
        echo "WiFi disconnected at $(date)"
        # Send alert (customize as needed)
        curl -X POST "YOUR_ALERT_ENDPOINT" -d "device=$HOSTNAME&status=disconnected"
    fi
    sleep 60
done
```

---

## Tips & Tricks

### Quick Connection Test

```bash
# Test internet connectivity
ping -c 3 8.8.8.8

# Test DNS resolution
ping -c 3 google.com

# Test cloud API
curl -I https://okmonitor-production.up.railway.app/health
```

### Forget All WiFi Networks

To start fresh:

```bash
# List all WiFi connections
nmcli -t -f NAME,TYPE connection show | grep 802-11-wireless | cut -d: -f1

# Delete each one
nmcli -t -f NAME,TYPE connection show | grep 802-11-wireless | cut -d: -f1 | \
    while read name; do sudo nmcli connection delete "$name"; done
```

### Export WiFi Configuration

To backup network settings:

```bash
# Backup all NetworkManager configs
sudo tar -czf wifi-backup.tar.gz /etc/NetworkManager/system-connections/

# Restore on another device
sudo tar -xzf wifi-backup.tar.gz -C /
sudo systemctl restart NetworkManager
```

### Auto-Connect to Best Network

NetworkManager automatically handles this based on:
1. Priority (higher = preferred)
2. Signal strength (if priorities equal)
3. Last connected time (if all else equal)

Configure priorities correctly and the system handles the rest!

---

## Common Questions

**Q: Can I use Ethernet and WiFi at the same time?**

A: Yes! NetworkManager handles both. Ethernet typically takes precedence automatically.

**Q: Does this work with WiFi 6 (802.11ax)?**

A: Yes, if your Raspberry Pi hardware and driver support it. The Raspberry Pi 5 built-in WiFi supports WiFi 5 (802.11ac).

**Q: Can I share WiFi via Ethernet (reverse tethering)?**

A: Yes, but requires additional configuration beyond this script. See NetworkManager connection sharing docs.

**Q: What if I need to configure WiFi before SSH access?**

A: Connect via Ethernet first, or use Raspberry Pi Imager to preconfigure WiFi before first boot.

**Q: Can I automate WiFi configuration during image creation?**

A: Yes! Add the network configuration to `/etc/NetworkManager/system-connections/` in your base image.

---

## Support

For issues with:
- **WiFi script**: Check this guide and troubleshooting section
- **NetworkManager**: See official docs at https://networkmanager.dev/
- **OK Monitor device**: See main DEPLOYMENT.md
- **Raspberry Pi WiFi**: See https://www.raspberrypi.com/documentation/

---

## Useful Commands Reference

```bash
# WiFi Script Commands
~/addwifi.sh "SSID" "password" [priority] [--hidden]
~/addwifi.sh --list
~/addwifi.sh --help

# NetworkManager Commands
nmcli device status                    # Show all network devices
nmcli device wifi list                 # Scan for WiFi networks
nmcli connection show                  # List saved connections
nmcli connection show --active         # Show active connections
nmcli connection up "Name"             # Connect to network
nmcli connection down "Name"           # Disconnect from network
nmcli connection delete "Name"         # Remove saved network

# Diagnostics
ip addr show wlan0                     # Show WiFi interface details
ping -c 3 8.8.8.8                      # Test internet connectivity
iwconfig wlan0                         # Show wireless configuration
sudo journalctl -u NetworkManager      # View NetworkManager logs
```

---

## Script Source

The `addwifi.sh` script is located in the OK Monitor repository:
- Source: `deployment/addwifi.sh`
- Installed to: `/home/{user}/addwifi.sh`
- Repository: https://github.com/atxapple/okmonitor

For updates, pull the latest version from the repository and re-run the installer.

---

Happy connecting!
