# Tailscale Remote Access for OK Monitor Fleet

This guide covers setting up Tailscale for secure remote SSH and VNC access to your OK Monitor devices.

## What is Tailscale?

Tailscale creates a secure, private network (called a "tailnet") that connects your devices no matter where they are. Benefits for OK Monitor fleet:

- ✅ **Secure** - Uses WireGuard encryption
- ✅ **Zero-config** - No port forwarding or firewall rules
- ✅ **Easy access** - SSH/VNC from anywhere (home, office, mobile)
- ✅ **Fleet management** - See all devices in one dashboard
- ✅ **Unique names** - Each device gets a memorable hostname
- ✅ **No public exposure** - Devices not accessible from internet

---

## Quick Start

### One-Time Setup (Tailscale Account)

1. Create free Tailscale account: https://tailscale.com/
2. Generate an auth key:
   - Go to https://login.tailscale.com/admin/settings/keys
   - Click "Generate auth key"
   - Enable "Reusable" for fleet deployment
   - Enable "Ephemeral" if you want device to disappear when offline
   - Copy the key (starts with `tskey-auth-...`)

### Install on Each Device

```bash
# On your Raspberry Pi
cd /opt/okmonitor
sudo chmod +x deployment/install_tailscale.sh

# Option 1: With auth key (recommended for fleet)
sudo deployment/install_tailscale.sh --auth-key tskey-auth-xxxxx

# Option 2: Interactive (opens browser for approval)
sudo deployment/install_tailscale.sh
```

### Install on Your Computer

**Mac/Windows:**
- Download from: https://tailscale.com/download
- Install and sign in with same account

**Linux:**
```bash
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up
```

---

## Device Naming Convention

Devices are automatically named: `okmonitor-{DEVICE_ID}`

Examples:
- `DEVICE_ID=okmonitor1` → Hostname: `okmonitor-okmonitor1`
- `DEVICE_ID=floor-01-cam` → Hostname: `okmonitor-floor-01-cam`
- `DEVICE_ID=warehouse-entrance` → Hostname: `okmonitor-warehouse-entrance`

This makes it easy to identify and access devices in your fleet.

---

## Accessing Devices

### SSH Access

From any device on your tailnet:

```bash
# By hostname
ssh mok@okmonitor-okmonitor1

# By Tailscale IP
ssh mok@100.101.102.103

# List all devices
tailscale status
```

### VNC Access

Raspberry Pi OS includes RealVNC Server (enabled by default).

**Using RealVNC Viewer:**
1. Download RealVNC Viewer: https://www.realvnc.com/en/connect/download/viewer/
2. Connect to: `okmonitor-okmonitor1` or Tailscale IP
3. Enter Raspberry Pi credentials

**Using built-in VNC clients:**
```bash
# macOS (Screen Sharing)
open vnc://okmonitor-okmonitor1

# Linux
vncviewer okmonitor-okmonitor1:5900
```

---

## Fleet Deployment Workflow

### Step 1: Prepare Auth Key

Generate one reusable auth key for all devices:
```
https://login.tailscale.com/admin/settings/keys
✓ Reusable
✓ Expires: 90 days (or longer)
```

### Step 2: Install on Multiple Devices

Save the auth key securely, then on each device:

```bash
cd /opt/okmonitor
export TAILSCALE_KEY="tskey-auth-xxxxx"
sudo deployment/install_tailscale.sh --auth-key "$TAILSCALE_KEY"
```

Or create a script for batch deployment:

```bash
#!/bin/bash
# deploy_fleet.sh
AUTH_KEY="tskey-auth-xxxxx"
DEVICES=("okmonitor1" "okmonitor2" "okmonitor3")

for device in "${DEVICES[@]}"; do
    echo "=== Deploying to $device ==="
    ssh mok@${device}.local "cd /opt/okmonitor && sudo deployment/install_tailscale.sh --auth-key $AUTH_KEY"
done
```

### Step 3: Manage Fleet

View all devices:
- Web: https://login.tailscale.com/admin/machines
- CLI: `tailscale status`

---

## Common Use Cases

### Remote Troubleshooting

```bash
# Check if device is online
tailscale status | grep okmonitor-okmonitor1

# SSH to device
ssh mok@okmonitor-okmonitor1

# Check device logs
ssh mok@okmonitor-okmonitor1 'sudo journalctl -u okmonitor-device -n 50'

# View live logs
ssh mok@okmonitor-okmonitor1 -t 'sudo journalctl -u okmonitor-device -f'
```

### Remote Configuration Updates

```bash
# Update .env.device
ssh mok@okmonitor-okmonitor1 'sudo nano /opt/okmonitor/.env.device'

# Restart service
ssh mok@okmonitor-okmonitor1 'sudo systemctl restart okmonitor-device'
```

### Batch Operations

```bash
# Check status of all devices
for host in okmonitor-okmonitor1 okmonitor-okmonitor2; do
    echo "=== $host ==="
    ssh mok@$host 'systemctl status okmonitor-device --no-pager | grep Active'
done

# Update all devices
for host in okmonitor-okmonitor1 okmonitor-okmonitor2; do
    echo "=== Updating $host ==="
    ssh mok@$host 'cd /opt/okmonitor && git pull && sudo systemctl restart okmonitor-device'
done
```

---

## Security Best Practices

### 1. Enable MFA on Tailscale Account

https://login.tailscale.com/admin/settings/mfa

Protects your entire fleet if account is compromised.

### 2. Use ACLs to Control Access

Define who can access which devices:

```json
// Example ACL (https://login.tailscale.com/admin/acls)
{
  "acls": [
    // Only admins can SSH to OK Monitor devices
    {
      "action": "accept",
      "src": ["group:admin"],
      "dst": ["tag:okmonitor:*"]
    }
  ],
  "tagOwners": {
    "tag:okmonitor": ["admin@example.com"]
  }
}
```

### 3. Set Auth Key Expiration

When generating auth keys, set reasonable expiration (30-90 days).

### 4. Regularly Review Connected Devices

https://login.tailscale.com/admin/machines

Remove unused or old devices.

### 5. Use Ephemeral Keys for Temporary Access

For short-term deployments, enable "Ephemeral" when generating auth keys.

---

## Troubleshooting

### Device Not Showing Up

```bash
# Check Tailscale status
sudo tailscale status

# Check if service is running
sudo systemctl status tailscaled

# Restart Tailscale
sudo tailscale down
sudo tailscale up
```

### Can't Connect to Device

```bash
# On the Raspberry Pi, check connectivity
sudo tailscale ping okmonitor-okmonitor2

# Check firewall (should be none on Raspberry Pi OS by default)
sudo iptables -L

# Verify SSH is running
sudo systemctl status ssh
```

### Hostname Not Resolving

Use Tailscale IP instead:
```bash
# Get device IP
tailscale ip -4

# Connect via IP
ssh mok@100.101.102.103
```

### Connection Drops Frequently

```bash
# Enable longer timeout
sudo tailscale up --timeout=0

# Check network stability
ping -c 10 8.8.8.8
```

### VNC Not Working

```bash
# Check if VNC is enabled (on Raspberry Pi)
sudo raspi-config
# → Interface Options → VNC → Enable

# Or via command line
sudo systemctl enable vncserver-x11-serviced.service
sudo systemctl start vncserver-x11-serviced.service

# Check VNC status
sudo systemctl status vncserver-x11-serviced.service
```

---

## Advanced Features

### Subnet Routing

Share Raspberry Pi's local network with your tailnet:

```bash
# Enable subnet routing
sudo tailscale up --advertise-routes=192.168.1.0/24

# Approve in Tailscale admin:
# https://login.tailscale.com/admin/machines → Edit route settings
```

Now you can access other devices on the Pi's network (router, cameras, etc.) through Tailscale.

### Exit Node

Use Raspberry Pi as VPN exit node:

```bash
# Enable as exit node
sudo tailscale up --advertise-exit-node

# Approve in admin panel
# On other devices: tailscale up --exit-node=okmonitor-okmonitor1
```

### SSH Certificates

For password-less access:

```bash
# On your computer
ssh-keygen -t ed25519 -C "okmonitor-fleet"

# Copy to device
ssh-copy-id mok@okmonitor-okmonitor1

# Test
ssh mok@okmonitor-okmonitor1  # No password needed
```

---

## Monitoring & Maintenance

### Check Connection Status

```bash
# On device
sudo tailscale status

# Get current IP
sudo tailscale ip -4

# View network info
sudo tailscale netcheck
```

### Update Tailscale

```bash
# On Raspberry Pi
sudo apt update
sudo apt upgrade tailscale

# Restart if needed
sudo systemctl restart tailscaled
```

### Remove Device from Tailnet

```bash
# Disconnect and remove
sudo tailscale logout

# Or from web dashboard:
# https://login.tailscale.com/admin/machines → Delete
```

---

## Integration with OK Monitor

Tailscale works seamlessly with OK Monitor:

- ✅ No changes to OK Monitor device service needed
- ✅ Device continues to communicate with Railway cloud
- ✅ Tailscale provides independent remote access layer
- ✅ Can be installed before or after device setup
- ✅ Uses same device ID for consistent naming

### Typical Deployment Order

1. Fresh Raspberry Pi OS installation
2. Run `deployment/install_device.sh` (OK Monitor)
3. Run `deployment/install_tailscale.sh` (Remote access)
4. Device is now monitored AND remotely accessible

---

## Cost & Limits

**Free Tier (Personal):**
- Up to 100 devices
- Up to 3 users
- Perfect for small OK Monitor fleets

**Paid Plans:**
- More devices
- Team collaboration features
- Advanced ACLs
- Priority support

See: https://tailscale.com/pricing

---

## Useful Resources

- Tailscale Docs: https://tailscale.com/kb/
- Admin Console: https://login.tailscale.com/admin/
- Status Page: https://status.tailscale.com/
- Community: https://forum.tailscale.com/

---

## Example: Complete Fleet Setup

```bash
# 1. Generate auth key (one time)
# Go to https://login.tailscale.com/admin/settings/keys
# Save key as: tskey-auth-xxxxx

# 2. Install on first device
ssh mok@okmonitor1.local
cd /opt/okmonitor
sudo deployment/install_tailscale.sh --auth-key tskey-auth-xxxxx

# 3. Install on additional devices
ssh mok@okmonitor2.local
cd /opt/okmonitor
sudo deployment/install_tailscale.sh --auth-key tskey-auth-xxxxx

# 4. From your laptop (with Tailscale installed)
tailscale status
# 100.101.102.103  okmonitor-okmonitor1  mok@  linux   -
# 100.101.102.104  okmonitor-okmonitor2  mok@  linux   -

# 5. Access any device
ssh mok@okmonitor-okmonitor1
ssh mok@okmonitor-okmonitor2

# 6. Manage fleet
ssh mok@okmonitor-okmonitor1 'sudo journalctl -u okmonitor-device --since today'
ssh mok@okmonitor-okmonitor2 'sudo systemctl status okmonitor-device'
```

---

## Support

For issues with:
- **Tailscale installation**: Check https://tailscale.com/kb/
- **OK Monitor device**: See main DEPLOYMENT.md
- **This script**: Review output and check logs

Happy remote monitoring! 🚀
