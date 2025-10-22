# Comitup WiFi Setup for OK Monitor

Easy WiFi configuration for Raspberry Pi devices without keyboard or monitor access.

---

## What is Comitup?

Comitup automatically creates a WiFi hotspot when your Raspberry Pi has no network connection, allowing you to configure WiFi through a simple web interface from your phone or laptop.

### Key Features

- ✅ **Zero-touch deployment**: No keyboard/monitor needed
- ✅ **Phone-friendly**: Configure from any device with WiFi
- ✅ **Open access point**: No password required for setup
- ✅ **Automatic fallback**: Returns to hotspot mode if WiFi fails
- ✅ **Multiple networks**: Save multiple WiFi configurations
- ✅ **Auto-reconnect**: Automatically connects to known networks

---

## Quick Start (Field Technician)

### First Time Setup - 3 Minutes

1. **Power on the Raspberry Pi**
   - Wait 60 seconds for boot

2. **Connect to the hotspot**
   - WiFi Network: `okmonitor-XXXX` (e.g., `okmonitor-1a2b`)
   - Password: **None** (open network)

3. **Open the configuration page**
   - Browser: `http://10.41.0.1`
   - You'll see the Comitup web interface

4. **Select customer WiFi**
   - Click on the customer's WiFi network name
   - Enter the WiFi password
   - Click "Connect"

5. **Wait for connection**
   - Device will connect to customer WiFi
   - Your phone will disconnect from the hotspot
   - Device is now online!

**That's it!** The device will remember this network and connect automatically.

---

## Installation

### Option 1: Automatic Installation (Recommended)

Run the installation script on your Raspberry Pi:

```bash
# Clone the repository
cd ~
git clone https://github.com/atxapple/okmonitor.git
cd okmonitor

# Run Comitup installer
sudo chmod +x deployment/install_comitup.sh
sudo deployment/install_comitup.sh

# Reboot to activate
sudo reboot
```

### Option 2: Manual Installation

Follow the official Comitup installation steps:

```bash
# Download repository package
cd /tmp
wget https://davesteele.github.io/comitup/deb/davesteele-comitup-apt-source_1.3_all.deb

# Install repository
sudo dpkg -i davesteele-comitup-apt-source*.deb

# Update and install Comitup
sudo apt-get update
sudo apt-get install comitup

# Configure (see Configuration section below)
sudo nano /etc/comitup.conf
```

---

## Configuration

### Basic Configuration

Edit `/etc/comitup.conf`:

```ini
# Access Point name when no WiFi is configured
# Format: okmonitor-NNNN where NNNN is auto-generated
ap_name: okmonitor

# Access Point password (empty = open/no password)
ap_password:

# Web service port
web_service: 80

# Callback script for state changes
external_callback: /usr/local/bin/comitup-callback.sh

# Enable verbose logging
verbose: false
```

### Custom Device Name

To use a specific device name in the hotspot:

```bash
sudo nano /etc/comitup.conf
```

Change:
```ini
ap_name: okmonitor-floor1
```

Restart:
```bash
sudo systemctl restart comitup
```

### Enable Password Protection (Optional)

If you need to secure the setup hotspot:

```bash
sudo nano /etc/comitup.conf
```

Add password (minimum 8 characters):
```ini
ap_password: your_secure_password
```

Restart:
```bash
sudo systemctl restart comitup
```

---

## Using Comitup

### Connecting to the Hotspot

When the device has no WiFi configured or can't connect to saved networks:

1. **Find the hotspot**
   - On your phone/laptop, scan for WiFi networks
   - Look for `okmonitor-XXXX` (where XXXX is auto-generated)

2. **Connect**
   - Select the network
   - No password required (unless configured)

3. **Access configuration**
   - Your browser may auto-open to the config page
   - If not, navigate to: `http://10.41.0.1`

### Web Interface

The Comitup web interface shows:

- **Available WiFi networks**: List of networks in range
- **Connected network**: Current WiFi connection (if any)
- **Signal strength**: For each available network
- **Connection status**: HOTSPOT, CONNECTING, or CONNECTED

### Configuring WiFi

From the web interface:

1. **Select network**
   - Click on the desired network name

2. **Enter password**
   - Type the WiFi password (if required)
   - Click "Connect"

3. **Wait**
   - Device will attempt to connect
   - May take 30-60 seconds
   - Your device will disconnect from the hotspot

4. **Verify**
   - Check that the device appears online
   - If it fails, it will return to hotspot mode

### Multiple Networks

Comitup can remember multiple networks:

1. Connect to first network (e.g., office WiFi)
2. When at a different location, reconnect to hotspot
3. Configure second network (e.g., warehouse WiFi)
4. Device will auto-connect to whichever is in range

---

## Command Line Interface

### Check Comitup Status

```bash
# Service status
systemctl status comitup

# Current state
comitup-cli

# View logs
journalctl -u comitup -f
```

### List Saved Networks

```bash
# Using NetworkManager (Comitup uses this underneath)
nmcli connection show

# Show only WiFi connections
nmcli connection show | grep wifi
```

### Delete a Network

```bash
# List connections
nmcli connection show

# Delete specific network
sudo nmcli connection delete "NetworkName"
```

### Force Hotspot Mode

Useful for testing or reconfiguration:

```bash
# Delete all WiFi connections
sudo nmcli connection show | grep wifi | awk '{print $1}' | \
    xargs -I {} sudo nmcli connection delete "{}"

# Reboot
sudo reboot

# Device will start in hotspot mode
```

### Manual Network Configuration

If the web interface isn't working:

```bash
# Add network manually
sudo nmcli device wifi connect "SSID" password "password"

# Verify connection
nmcli device status
```

---

## Integration with OK Monitor

### Automatic Service Restart

The installation script includes a callback that restarts OK Monitor when WiFi connects:

```bash
# Callback script location
/usr/local/bin/comitup-callback.sh
```

This ensures OK Monitor starts using the new network connection immediately.

### Pre-Installation with OK Monitor

To include Comitup in your OK Monitor device setup:

```bash
# Install Comitup first
sudo deployment/install_comitup.sh

# Then install OK Monitor
sudo deployment/install_device.sh

# Both services will work together
```

### Deployment Workflow

**For fleet deployments:**

1. Create golden image with Comitup pre-installed
2. Clone image to SD cards
3. Boot devices at customer sites
4. Use Comitup to configure local WiFi
5. OK Monitor automatically starts after WiFi connects

See [CLONING.md](CLONING.md) for image cloning details.

---

## Troubleshooting

### Hotspot Not Appearing

**Check Comitup service:**
```bash
sudo systemctl status comitup
```

**If not running:**
```bash
sudo systemctl start comitup
```

**Check WiFi interface:**
```bash
nmcli device status
```

**Restart Comitup:**
```bash
sudo systemctl restart comitup
```

### Can't Access Web Interface

**Verify IP address:**
```bash
# When connected to hotspot, device should be at:
# 10.41.0.1
```

**Try these URLs:**
- http://10.41.0.1
- http://10.41.0.1:80
- http://comitup.local (may work on some devices)

**Clear browser cache:**
- Try incognito/private browsing mode
- Try a different browser

**Check firewall:**
```bash
# Ensure port 80 is accessible
sudo ufw status
```

### WiFi Connection Fails

**Check password:**
- Retype carefully (passwords are case-sensitive)
- Check for special characters

**Check signal strength:**
- Move device closer to WiFi router
- Ensure router is working

**View connection logs:**
```bash
sudo journalctl -u comitup -n 50
```

**Try manual connection:**
```bash
sudo nmcli device wifi connect "SSID" password "password"
```

### Device Stuck in Hotspot Mode

**Check saved connections:**
```bash
nmcli connection show
```

**If connection exists but not connecting:**
```bash
# Try to activate manually
sudo nmcli connection up "NetworkName"

# Check why it failed
sudo journalctl -u NetworkManager -n 50
```

**Signal too weak:**
- Move device closer to router
- Check antenna connections (if using USB WiFi)
- Consider WiFi extender

**Network changed:**
- If router was replaced or password changed
- Reconnect to hotspot and reconfigure

### Hotspot Keeps Disconnecting

**Check for WiFi interference:**
```bash
# Scan for congested channels
sudo iwlist wlan0 scan | grep -E "Channel|ESSID|Quality"
```

**Change hotspot channel (if needed):**
```bash
sudo nano /etc/comitup.conf
# Add: ap_channel: 6
sudo systemctl restart comitup
```

**Check power supply:**
- Ensure adequate power (5V 3A for Pi 5)
- Poor power can cause WiFi instability

---

## Advanced Configuration

### Custom Web Portal Port

To change from default port 80:

```bash
sudo nano /etc/comitup.conf
```

Change:
```ini
web_service: 8080
```

Access at: `http://10.41.0.1:8080`

### Enable Verbose Logging

For debugging connection issues:

```bash
sudo nano /etc/comitup.conf
```

Enable:
```ini
verbose: true
```

Restart and view logs:
```bash
sudo systemctl restart comitup
sudo journalctl -u comitup -f
```

### Custom Callback Script

The callback script is triggered on state changes:

```bash
sudo nano /usr/local/bin/comitup-callback.sh
```

States:
- `HOTSPOT`: No WiFi configured, running as AP
- `CONNECTING`: Attempting to connect to WiFi
- `CONNECTED`: Successfully connected to WiFi
- `FAILED`: Connection attempt failed

Example custom actions:
```bash
#!/bin/bash
STATE=$1

case "$STATE" in
    CONNECTED)
        # Custom actions when WiFi connects
        systemctl restart okmonitor-device
        logger "OK Monitor: WiFi connected"
        ;;
    FAILED)
        # Alert on connection failure
        logger "OK Monitor: WiFi connection failed"
        # Could send alert via cellular modem, etc.
        ;;
esac
```

### Disable NetworkManager Control

If you need to manage networking differently:

```bash
sudo systemctl stop comitup
sudo systemctl disable comitup
```

---

## Comparison with Other Methods

### vs. addwifi.sh (NetworkManager script)

| Feature | Comitup | addwifi.sh |
|---------|---------|------------|
| **Setup access** | Phone/web browser | SSH access required |
| **Ease of use** | Very easy (web UI) | Command line |
| **No credentials** | Works without SSH | Requires SSH login |
| **Best for** | On-site technicians | Remote IT/admins |
| **Hotspot mode** | Automatic | Manual |
| **Learning curve** | Minimal | Medium |

**Recommendation**: Use Comitup for field deployment, addwifi.sh for remote management.

### vs. Mobile Hotspot Method

| Feature | Comitup | Mobile Hotspot |
|---------|---------|----------------|
| **Pre-config needed** | None | Hotspot credentials |
| **Device dependency** | None | Phone required |
| **Technician training** | Minimal | Must know hotspot setup |
| **Best for** | Any deployment | Trained technicians |

**Recommendation**: Comitup is simpler and more flexible.

### Combined Approach

For maximum flexibility:

```bash
# Install both Comitup and addwifi.sh
sudo deployment/install_comitup.sh
sudo deployment/install_device.sh  # Includes addwifi.sh

# Use Comitup for on-site WiFi setup
# Use addwifi.sh for remote WiFi changes via SSH/Tailscale
```

---

## Security Considerations

### Open Access Point Risks

The default configuration uses an open (no password) access point for ease of setup.

**Risks:**
- Anyone can connect to the hotspot
- Anyone can configure WiFi settings
- Limited attack window (only active when no WiFi configured)

**Mitigations:**
1. **Physical security**: Keep devices in secure areas during setup
2. **Limited exposure**: Hotspot only active briefly during deployment
3. **Monitor access**: Check logs for unexpected connections
4. **Add password**: For high-security environments

### Adding Password Protection

For sensitive deployments:

```bash
sudo nano /etc/comitup.conf
```

Set:
```ini
ap_password: SecurePass123!
```

Document this password in your deployment procedures.

### Network Isolation

Comitup hotspot is isolated from your main network:
- Hotspot is its own network (10.41.0.0/24)
- No access to your configured WiFi
- Only provides web interface for configuration

### Disable After Deployment

If you want to disable Comitup after initial setup:

```bash
sudo systemctl disable comitup
sudo systemctl stop comitup
```

Re-enable if needed:
```bash
sudo systemctl enable comitup
sudo systemctl start comitup
sudo reboot
```

---

## Monitoring & Maintenance

### Check Comitup Health

Create a monitoring script:

```bash
#!/bin/bash
# comitup-health.sh

STATUS=$(comitup-cli 2>/dev/null)

if [[ $STATUS == *"CONNECTED"* ]]; then
    echo "OK: Device connected to WiFi"
    exit 0
elif [[ $STATUS == *"HOTSPOT"* ]]; then
    echo "WARN: Device in hotspot mode (no WiFi configured)"
    exit 1
else
    echo "ERROR: Comitup not responding"
    exit 2
fi
```

### Log Monitoring

Watch for connection issues:

```bash
# Monitor Comitup logs
sudo journalctl -u comitup -f

# Check for failures
sudo journalctl -u comitup | grep -i "fail\|error"
```

### Automatic Fallback

Comitup automatically falls back to hotspot mode if:
- Configured WiFi network not in range
- WiFi password changed
- Network authentication fails
- Connection drops repeatedly

This provides automatic recovery without manual intervention.

---

## Common Deployment Scenarios

### Scenario 1: New Site Installation

**Technician arrives with unconfigured device:**

1. Power on device
2. Connect phone to `okmonitor-XXXX` hotspot
3. Open http://10.41.0.1
4. Select customer WiFi and enter password
5. Device connects, OK Monitor starts automatically
6. Technician verifies monitoring is working
7. Done!

**Time: ~3 minutes**

### Scenario 2: WiFi Password Changed

**Customer changed their WiFi password:**

1. Device loses connection, returns to hotspot mode
2. Technician connects to `okmonitor-XXXX`
3. Opens http://10.41.0.1
4. Re-enters new WiFi password
5. Device reconnects with new credentials

**No need to access the device physically!**

### Scenario 3: Device Relocation

**Moving device to different location:**

1. Power off, move device
2. Power on at new location
3. Device tries old WiFi (not available)
4. Automatically switches to hotspot mode
5. Configure new location's WiFi
6. Resumes monitoring

**Works across unlimited locations!**

### Scenario 4: Multi-Site Device

**Device moves between warehouse and office:**

1. Connect to warehouse WiFi via Comitup
2. Later, connect to office WiFi via Comitup
3. Device remembers both networks
4. Auto-connects to whichever is in range
5. Seamless operation in both locations

---

## FAQs

**Q: How long does the device stay in hotspot mode?**

A: Indefinitely, until you configure WiFi. Once WiFi is configured and connecting successfully, the hotspot disappears.

**Q: Can I configure multiple WiFi networks?**

A: Yes! Connect to different networks at different times. Comitup saves all configurations.

**Q: What if the device can't see any WiFi networks?**

A: Check that WiFi hardware is working (`nmcli device status`). The web interface will show "No networks found" if WiFi scanning isn't working.

**Q: Does this work with hidden WiFi networks?**

A: Yes, but you'll need to use the command line:
```bash
sudo nmcli device wifi connect "HiddenSSID" password "password" hidden yes
```

**Q: Can I use Ethernet and WiFi simultaneously?**

A: Yes, both can be active. Ethernet typically takes priority for routing.

**Q: What happens if both WiFi and Ethernet are connected?**

A: Both work, but the system prefers Ethernet for outbound connections. WiFi remains configured and will be used if Ethernet fails.

**Q: Is Comitup compatible with VPNs (like Tailscale)?**

A: Yes! Comitup manages the base network connection. Tailscale and other VPNs work on top of that.

**Q: Can I access the web interface after WiFi is configured?**

A: No, the hotspot and web interface are only active when the device isn't connected to WiFi. Use SSH or Tailscale for remote management.

**Q: How do I change the hotspot name?**

A: Edit `/etc/comitup.conf`, change `ap_name`, and restart comitup service.

---

## Resources

### Official Documentation
- Comitup GitHub: https://github.com/davesteele/comitup
- Comitup Docs: https://davesteele.github.io/comitup/

### OK Monitor Documentation
- Main Deployment: [DEPLOYMENT.md](DEPLOYMENT.md)
- WiFi Script: [WIFI.md](WIFI.md)
- On-site Setup: [ONSITE-SETUP.md](ONSITE-SETUP.md)
- Tailscale Remote Access: [TAILSCALE.md](TAILSCALE.md)

### File Locations
- Configuration: `/etc/comitup.conf`
- Callback script: `/usr/local/bin/comitup-callback.sh`
- Service: `/lib/systemd/system/comitup.service`
- Logs: `journalctl -u comitup`

---

## Support

For issues:
1. Check service status: `systemctl status comitup`
2. View logs: `journalctl -u comitup -f`
3. Review troubleshooting section above
4. Check official docs: https://davesteele.github.io/comitup/
5. OK Monitor issues: See main DEPLOYMENT.md

---

Happy configuring!
