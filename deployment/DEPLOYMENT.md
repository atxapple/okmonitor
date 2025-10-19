# Raspberry Pi 5 Deployment Guide

This guide covers deploying the OK Monitor device program on Raspberry Pi 5 with Bookworm OS.

## Features

- ✅ Auto-start after network is available
- ✅ Automatic daily restart at 2:00 AM for updates
- ✅ USB webcam support
- ✅ Automatic git pull for software updates
- ✅ Systemd service management
- ✅ Comprehensive logging

---

## Prerequisites

- Raspberry Pi 5 with Raspberry Pi OS (Bookworm) 64-bit
- USB webcam connected
- Internet connection
- Railway or cloud-hosted API server
- Git repository access

---

## Quick Installation

### 1. Download and run installation script

```bash
# On your Raspberry Pi
cd ~
git clone https://github.com/atxapple/okmonitor.git
cd okmonitor
sudo chmod +x deployment/install_device.sh
sudo deployment/install_device.sh
```

### 2. Configure the device

Edit the environment file with your settings:

```bash
sudo nano /opt/okmonitor/.env.device
```

**Required configuration:**
```bash
# Your Railway or cloud API URL
API_URL=https://okmonitor-production.up.railway.app

# Unique device identifier
DEVICE_ID=floor-01-cam

# Camera device (usually 0 for first USB camera)
CAMERA_SOURCE=0
```

### 3. Test the service

```bash
# Start the service
sudo systemctl start okmonitor-device

# Watch the logs
sudo journalctl -u okmonitor-device -f

# You should see:
# [device] Entering scheduled capture mode...
# [device] Received new config: {...}
```

Press `Ctrl+C` to stop watching logs.

### 4. Enable auto-start

```bash
# The service is already enabled by install script
# Verify it's enabled:
sudo systemctl is-enabled okmonitor-device

# Check status
sudo systemctl status okmonitor-device
```

### 5. Verify update timer

```bash
# Check that the update timer is scheduled
sudo systemctl list-timers okmonitor-update

# You should see it scheduled for 02:00 daily
```

### 6. Reboot and verify

```bash
sudo reboot
```

After reboot, wait 30 seconds then check:

```bash
# Should show "active (running)"
sudo systemctl status okmonitor-device

# Should show recent logs
sudo journalctl -u okmonitor-device --since "5 minutes ago"
```

---

## Manual Operations

### View Logs

```bash
# Live tail
sudo journalctl -u okmonitor-device -f

# Last 100 lines
sudo journalctl -u okmonitor-device -n 100

# Logs since yesterday
sudo journalctl -u okmonitor-device --since yesterday

# Update logs
sudo journalctl -u okmonitor-update --since yesterday
```

### Service Control

```bash
# Start
sudo systemctl start okmonitor-device

# Stop
sudo systemctl stop okmonitor-device

# Restart
sudo systemctl restart okmonitor-device

# Disable auto-start
sudo systemctl disable okmonitor-device

# Re-enable auto-start
sudo systemctl enable okmonitor-device
```

### Manual Update

```bash
# Run update script manually
sudo /opt/okmonitor/deployment/update_device.sh

# View update logs
sudo cat /var/log/okmonitor-update.log
```

### Check Update Timer

```bash
# List all timers
sudo systemctl list-timers

# Check specific timer status
sudo systemctl status okmonitor-update.timer

# Manually trigger update now (for testing)
sudo systemctl start okmonitor-update.service
```

---

## Troubleshooting

### Service won't start

```bash
# Check detailed status
sudo systemctl status okmonitor-device

# Check if camera is accessible
ls -l /dev/video*
v4l2-ctl --list-devices

# Verify pi user is in video group
groups pi

# If not, add and reboot:
sudo usermod -a -G video pi
sudo reboot
```

### Camera not found

```bash
# List video devices
v4l2-ctl --list-devices

# Test camera with v4l2
v4l2-ctl --device=/dev/video0 --all

# If camera is /dev/video1, edit .env.device:
sudo nano /opt/okmonitor/.env.device
# Change: CAMERA_SOURCE=1
sudo systemctl restart okmonitor-device
```

### Network connection fails

```bash
# Check if API URL is reachable
curl -I https://okmonitor-production.up.railway.app

# Check DNS resolution
nslookup okmonitor-production.up.railway.app

# Check network status
ip addr
ping -c 4 8.8.8.8
```

### Updates not happening

```bash
# Check timer status
sudo systemctl status okmonitor-update.timer

# Check if timer is enabled
sudo systemctl is-enabled okmonitor-update.timer

# If not enabled:
sudo systemctl enable okmonitor-update.timer

# Check last run
sudo journalctl -u okmonitor-update.service -n 50

# Manually test update
sudo /opt/okmonitor/deployment/update_device.sh
```

### High CPU or memory usage

```bash
# Check resource usage
htop
# or
top

# View service resource limits
systemctl show okmonitor-device | grep -i memory
systemctl show okmonitor-device | grep -i cpu

# Adjust limits in service file if needed
sudo nano /etc/systemd/system/okmonitor-device.service
# Modify MemoryMax= and CPUQuota= values
sudo systemctl daemon-reload
sudo systemctl restart okmonitor-device
```

### Disk space issues

```bash
# Check disk usage
df -h

# Check debug captures size
du -sh /opt/okmonitor/debug_captures

# Clean old debug captures (older than 7 days)
find /opt/okmonitor/debug_captures -type f -mtime +7 -delete

# Or disable debug captures:
sudo nano /opt/okmonitor/.env.device
# Set: SAVE_FRAMES_DIR=
sudo systemctl restart okmonitor-device
```

---

## Configuration Reference

### Environment Variables (.env.device)

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `API_URL` | Yes | - | Cloud API endpoint (Railway/cloud URL) |
| `DEVICE_ID` | Yes | - | Unique device identifier |
| `CAMERA_SOURCE` | No | `0` | Camera device number (/dev/video0 = 0) |
| `CAMERA_WARMUP` | No | `3` | Frames to discard on camera startup |
| `API_TIMEOUT` | No | `30` | API request timeout in seconds |
| `CONFIG_POLL_INTERVAL` | No | `5.0` | How often to check cloud config (seconds) |
| `SAVE_FRAMES_DIR` | No | `/opt/okmonitor/debug_captures` | Debug frame storage (empty = disabled) |
| `CAMERA_RESOLUTION` | No | - | Force resolution (e.g., `1920x1080`) |
| `CAMERA_BACKEND` | No | - | OpenCV backend (e.g., `v4l2`) |

### Systemd Service Files

- **okmonitor-device.service**: Main device service (auto-starts on boot)
- **okmonitor-update.service**: Update execution service
- **okmonitor-update.timer**: Schedules updates at 02:00 daily

### File Locations

- Installation: `/opt/okmonitor/`
- Configuration: `/opt/okmonitor/.env.device`
- Logs: `journalctl -u okmonitor-device`
- Update logs: `/var/log/okmonitor-update.log`
- Debug captures: `/opt/okmonitor/debug_captures/`
- Service files: `/etc/systemd/system/okmonitor-*.service`

---

## Security Considerations

### SSH Hardening

```bash
# Disable password authentication (use SSH keys only)
sudo nano /etc/ssh/sshd_config
# Set: PasswordAuthentication no
sudo systemctl restart sshd
```

### Firewall Setup

```bash
# Install UFW
sudo apt install ufw

# Allow SSH
sudo ufw allow 22/tcp

# Enable firewall
sudo ufw enable

# Check status
sudo ufw status
```

### Automatic Security Updates

```bash
# Install unattended-upgrades
sudo apt install unattended-upgrades

# Enable automatic security updates
sudo dpkg-reconfigure -plow unattended-upgrades
```

---

## Monitoring & Maintenance

### Log Rotation

Logs are automatically managed by systemd's journald. To check space:

```bash
# Check journal size
journalctl --disk-usage

# Clean logs older than 7 days
sudo journalctl --vacuum-time=7d
```

### Debug Capture Cleanup

Add a cron job to clean old captures:

```bash
# Edit crontab
sudo crontab -e

# Add line to clean files older than 7 days at 3 AM daily
0 3 * * * find /opt/okmonitor/debug_captures -type f -mtime +7 -delete
```

### Health Monitoring

Create a simple health check script:

```bash
sudo nano /opt/okmonitor/health_check.sh
```

```bash
#!/bin/bash
# Simple health check
if systemctl is-active --quiet okmonitor-device; then
    echo "OK: Service is running"
    exit 0
else
    echo "ERROR: Service is not running"
    exit 1
fi
```

```bash
sudo chmod +x /opt/okmonitor/health_check.sh
```

---

## Advanced Configuration

### Change Update Time

Edit the timer file to change update time from 02:00:

```bash
sudo nano /etc/systemd/system/okmonitor-update.timer
# Modify OnCalendar= line (e.g., OnCalendar=*-*-* 04:00:00 for 4 AM)
sudo systemctl daemon-reload
sudo systemctl restart okmonitor-update.timer
```

### Multiple Devices

To run multiple camera devices on one Pi:

1. Create separate service files (okmonitor-device-1.service, okmonitor-device-2.service)
2. Create separate .env files (.env.device-1, .env.device-2)
3. Use different DEVICE_ID and CAMERA_SOURCE for each

---

## Uninstallation

```bash
# Stop and disable services
sudo systemctl stop okmonitor-device
sudo systemctl disable okmonitor-device
sudo systemctl stop okmonitor-update.timer
sudo systemctl disable okmonitor-update.timer

# Remove service files
sudo rm /etc/systemd/system/okmonitor-*.service
sudo rm /etc/systemd/system/okmonitor-*.timer
sudo systemctl daemon-reload

# Remove installation directory
sudo rm -rf /opt/okmonitor

# Remove logs
sudo journalctl --vacuum-time=1s
```

---

## Support

For issues or questions:
1. Check the logs: `sudo journalctl -u okmonitor-device -f`
2. Review troubleshooting section above
3. Open an issue on GitHub
4. Check cloud API server status

---

## Changelog

- **2025-01-XX**: Initial deployment documentation
  - Systemd service with network dependency
  - Automatic updates at 02:00 AM
  - USB webcam support
  - Resource limits and security hardening
