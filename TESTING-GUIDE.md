# Testing Guide - Image Optimization Features

## Quick Health Check

Run these commands to verify the optimization features are working:

---

## 1. Device Side - Thumbnail Generation

### On Raspberry Pi Device

```bash
# SSH to your test device
ssh mok@okmonitor.local

# Check the device code has thumbnail support
cd /opt/okmonitor
git status
git log --oneline -1

# Should show commit from dev branch

# Restart the device service to ensure latest code
sudo systemctl restart okmonitor-device

# Watch the logs
sudo journalctl -u okmonitor-device -f

# Look for messages about thumbnail generation
# You should see log entries showing frame sizes
```

**What to look for:**
- Service starts without errors
- Camera captures frames
- No errors about thumbnail generation

### Manual Test - Check Thumbnail Size

```bash
# Trigger a manual capture
curl -X POST "http://your-dev-server/v1/manual-trigger?device_id=your-device-id"

# On the device, check the debug captures (if enabled)
ls -lh /opt/okmonitor/debug_captures/

# Compare file sizes - you should see thumbnail is much smaller
# Example:
# -rw-r--r-- 1 mok mok 1.2M Jan 22 10:30 1234567890_manual.jpeg  (full)
# (thumbnails are sent to server, not saved locally by default)
```

---

## 2. Server Side - Thumbnail Storage

### Check Server Logs

```bash
# If using Railway
railway logs --environment dev

# Or SSH to server
tail -f /var/log/okmonitor-server.log

# Look for:
# - "thumbnail_base64" in capture payloads
# - "Thumbnail stored" or similar messages
```

### Check Datalake Storage

```bash
# SSH to server or check Railway volume
cd /mnt/data/datalake  # or your datalake path

# Navigate to today's captures
cd $(date +%Y/%m/%d)

# List files
ls -lh

# You should see pairs of files:
# device-id_timestamp_hash.jpeg         (full image ~1MB)
# device-id_timestamp_hash_thumb.jpeg   (thumbnail ~100KB)
```

**Expected output:**
```bash
-rw-r--r-- 1 user user 1.2M Jan 22 10:30 okmonitor1_20250122T103045678901Z_abc12345.jpeg
-rw-r--r-- 1 user user  85K Jan 22 10:30 okmonitor1_20250122T103045678901Z_abc12345_thumb.jpeg
-rw-r--r-- 1 user user 2.1K Jan 22 10:30 okmonitor1_20250122T103045678901Z_abc12345.json
```

### Check Metadata JSON

```bash
# View a metadata file
cat okmonitor1_20250122T103045678901Z_abc12345.json | jq .

# Should contain:
{
  "record_id": "okmonitor1_20250122T103045678901Z_abc12345",
  "image_stored": true,
  "image_filename": "okmonitor1_20250122T103045678901Z_abc12345.jpeg",
  "thumbnail_stored": true,
  "thumbnail_filename": "okmonitor1_20250122T103045678901Z_abc12345_thumb.jpeg",
  ...
}
```

---

## 3. API Endpoints - Thumbnail Serving

### Test Thumbnail Endpoint

```bash
# Get a record_id from the datalake
RECORD_ID="okmonitor1_20250122T103045678901Z_abc12345"

# Test the thumbnail endpoint
curl -I "http://your-dev-server/v1/captures/$RECORD_ID/thumbnail"

# Expected response:
HTTP/1.1 200 OK
content-type: image/jpeg
cache-control: public, max-age=86400
content-length: 87432
```

### Download and Verify Thumbnail

```bash
# Download thumbnail
curl "http://your-dev-server/v1/captures/$RECORD_ID/thumbnail" -o thumbnail.jpeg

# Check file size
ls -lh thumbnail.jpeg
# Should be ~50-150KB

# View the image (if you have image viewer)
open thumbnail.jpeg  # macOS
xdg-open thumbnail.jpeg  # Linux
start thumbnail.jpeg  # Windows
```

### Compare Thumbnail vs Full Image

```bash
# Download full image (if you have an endpoint for it)
# Or copy from datalake
cp /mnt/data/datalake/2025/01/22/$RECORD_ID.jpeg full.jpeg

# Compare sizes
ls -lh full.jpeg thumbnail.jpeg

# Should see ~90% reduction
# full.jpeg:      1.2M
# thumbnail.jpeg:  120K
```

---

## 4. WebSocket - Real-Time Notifications

### Test WebSocket Connection

```bash
# Install wscat if not already installed
npm install -g wscat

# Or use websocat
# wget https://github.com/vi/websocat/releases/download/v1.11.0/websocat.x86_64-unknown-linux-musl
# chmod +x websocat.x86_64-unknown-linux-musl

# Connect to WebSocket
wscat -c 'ws://your-dev-server/ws/captures?device_id=all'

# You should see:
Connected (press CTRL+C to quit)
< {"event":"connected","target":"__all__"}
```

### Test Real-Time Notifications

Keep the WebSocket connection open, then:

```bash
# In another terminal, trigger a capture
curl -X POST "http://your-dev-server/v1/manual-trigger?device_id=your-device-id"

# In the WebSocket terminal, you should immediately see:
< {"event":"capture","device_id":"your-device-id","record_id":"...","state":"normal","captured_at":"..."}
```

**Success criteria:**
- ✅ Message arrives within 1 second
- ✅ Contains record_id, device_id, state
- ✅ Multiple captures show multiple messages

### Test WebSocket Persistence

```bash
# Keep WebSocket open for 5 minutes
# Send captures every 30 seconds
# WebSocket should stay connected and receive all messages

# Check for:
# - No disconnections
# - All captures received
# - No duplicate messages
```

---

## 5. Browser Testing - Network Inspection

### Using Chrome DevTools

1. **Open Dashboard:**
   ```
   http://your-dev-server/ui
   ```

2. **Open DevTools:**
   - Press F12 or Cmd+Option+I (Mac)
   - Go to "Network" tab

3. **Filter to see WebSocket:**
   - Click "WS" filter
   - Refresh page
   - Should see WebSocket connection to `/ws/captures`

4. **Check WebSocket Messages:**
   - Click on the WebSocket connection
   - Go to "Messages" tab
   - Trigger a capture
   - Should see message arrive immediately

5. **Check Image Loading:**
   - Click "Img" filter
   - Look for requests to `/v1/captures/{id}/thumbnail`
   - Check response size (should be small ~100KB)
   - Check caching (second load should be from cache)

### Network Performance

**Before optimization (baseline):**
```
Full image load: 1.2MB × 10 captures = 12MB
Load time: ~5-10 seconds on 3G
```

**After optimization (with thumbnails):**
```
Thumbnail load: 100KB × 10 captures = 1MB
Load time: <1 second on 3G
```

---

## 6. End-to-End Test

### Complete Flow Test

```bash
# 1. Start with clean state
# Delete old captures or use new device_id

# 2. Connect WebSocket monitoring
wscat -c 'ws://your-dev-server/ws/captures?device_id=all' &

# 3. Trigger capture from device
curl -X POST "http://your-dev-server/v1/manual-trigger?device_id=test-device"

# 4. Verify each step:
```

**Expected flow:**
1. ✅ Device receives trigger
2. ✅ Device captures image
3. ✅ Device generates thumbnail
4. ✅ Device sends both to server (check network traffic)
5. ✅ Server receives and decodes both
6. ✅ Server stores both in datalake
7. ✅ Server publishes WebSocket event
8. ✅ WebSocket client receives notification
9. ✅ Thumbnail endpoint serves thumbnail
10. ✅ Full image available on demand

---

## 7. Performance Benchmarks

### Measure Thumbnail Generation Time

```python
# Add to device code temporarily for testing
import time

start = time.time()
thumbnail = create_thumbnail(full_image, max_size=(400, 300), quality=85)
duration = time.time() - start

print(f"Thumbnail generation took: {duration*1000:.2f}ms")
print(f"Original size: {len(full_image)} bytes")
print(f"Thumbnail size: {len(thumbnail)} bytes")
print(f"Reduction: {(1 - len(thumbnail)/len(full_image))*100:.1f}%")
```

**Expected results:**
- Generation time: <100ms on Raspberry Pi 5
- Size reduction: 85-95%

### Measure WebSocket Latency

```bash
# Record timestamp when triggering
START=$(date +%s.%N)

# Trigger capture
curl -X POST "http://your-dev-server/v1/manual-trigger?device_id=test"

# Note when WebSocket message arrives
END=$(date +%s.%N)

# Calculate latency
echo "Latency: $(echo "$END - $START" | bc) seconds"
```

**Expected latency:**
- <1 second from trigger to WebSocket notification
- <2 seconds including device capture time

---

## 8. Load Testing

### Concurrent Captures

```bash
# Simulate multiple devices
for i in {1..10}; do
  curl -X POST "http://your-dev-server/v1/manual-trigger?device_id=device-$i" &
done

# Monitor:
# - Server CPU/RAM usage
# - All WebSocket clients receive events
# - All thumbnails stored correctly
# - No errors in logs
```

### WebSocket Connection Limit

```bash
# Open many WebSocket connections
for i in {1..50}; do
  wscat -c 'ws://your-dev-server/ws/captures?device_id=all' &
done

# Trigger captures
curl -X POST "http://your-dev-server/v1/manual-trigger?device_id=test"

# Check:
# - All connections receive messages
# - Server handles load gracefully
# - No connection drops
```

---

## 9. Error Scenarios

### Test Graceful Degradation

**Missing thumbnail (old device):**
```bash
# Send capture without thumbnail_base64
curl -X POST "http://your-dev-server/v1/captures" \
  -H "Content-Type: application/json" \
  -d '{
    "device_id": "test",
    "trigger_label": "manual",
    "image_base64": "..."
  }'

# Should still work, just no thumbnail stored
```

**Corrupted thumbnail:**
```bash
# Send invalid base64
curl -X POST "http://your-dev-server/v1/captures" \
  -H "Content-Type: application/json" \
  -d '{
    "device_id": "test",
    "trigger_label": "manual",
    "image_base64": "...",
    "thumbnail_base64": "invalid-base64!!!"
  }'

# Should log warning but still process full image
```

**Thumbnail not found:**
```bash
# Request non-existent thumbnail
curl -I "http://your-dev-server/v1/captures/fake-record-id/thumbnail"

# Should return 404
HTTP/1.1 404 Not Found
```

---

## 10. Dashboard Visual Check

### Open Dashboard

```
http://your-dev-server/ui
```

### Check for Issues:

**Console (F12):**
- ✅ No JavaScript errors
- ✅ WebSocket connection established
- ✅ WebSocket messages received

**Network Tab:**
- ✅ Thumbnails loading (~100KB each)
- ✅ Cache headers present
- ✅ Second load from cache (0 bytes transferred)

**Visual:**
- ✅ Images display correctly
- ✅ No broken image icons
- ✅ Page loads quickly
- ✅ New captures appear automatically (WebSocket)

---

## Quick Checklist

Copy this checklist for testing:

```
Device Side:
[ ] Device service starts without errors
[ ] Captures work normally
[ ] No errors in device logs

Server Side:
[ ] Both full images and thumbnails stored in datalake
[ ] Metadata JSON has thumbnail_stored: true
[ ] Server logs show no errors

API Endpoints:
[ ] GET /v1/captures/{id}/thumbnail returns 200
[ ] Thumbnail file is ~10% size of full image
[ ] Cache-Control headers present

WebSocket:
[ ] Connection establishes successfully
[ ] Receives connected message
[ ] Receives capture events in real-time
[ ] No disconnections during normal use

Performance:
[ ] Thumbnail generation <100ms
[ ] WebSocket notification <1 second
[ ] Dashboard initial load fast
[ ] Bandwidth reduced by ~90% for thumbnails

Dashboard:
[ ] No JavaScript errors
[ ] Images display correctly
[ ] Real-time updates work
[ ] Responsive on mobile
```

---

## Troubleshooting

### Thumbnails Not Generated

**Check:**
```bash
# Device has OpenCV installed?
python3 -c "import cv2; print(cv2.__version__)"

# Capture code has thumbnail support?
grep -r "create_thumbnail" /opt/okmonitor/device/

# Service restarted after update?
sudo systemctl restart okmonitor-device
```

### Thumbnails Not Stored

**Check:**
```bash
# Server received thumbnail_base64?
# Check server logs for "thumbnail" keyword

# Datalake permissions correct?
ls -la /mnt/data/datalake/

# Disk space available?
df -h /mnt/data
```

### WebSocket Not Connecting

**Check:**
```bash
# WebSocket endpoint available?
curl -I "http://your-dev-server/ws/captures"

# Firewall blocking WebSocket?
# Check port 8000 or your server port

# Server supports WebSocket?
# Check fastapi version: pip show fastapi
```

### Dashboard Not Updating

**Check browser console:**
- WebSocket connection status
- JavaScript errors
- Network requests

**Check server:**
- CaptureHub publishing events?
- WebSocket endpoint working?

---

## Success Criteria

✅ **Feature is working correctly if:**

1. Devices generate thumbnails automatically
2. Server stores both full images and thumbnails
3. Metadata tracks thumbnail storage
4. Thumbnail endpoint serves images with cache headers
5. WebSocket delivers notifications within 1 second
6. Dashboard loads thumbnails 10x faster than full images
7. No errors in device, server, or browser logs
8. Backwards compatible with old devices/captures

---

**Last Updated:** 2025-01-22
**Branch:** dev
**Status:** Ready for testing
