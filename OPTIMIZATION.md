# Image Loading Optimization Feature

**Branch:** `feature/optimize-image-loading`

## Overview

This feature dramatically improves dashboard performance and reduces network usage through:
1. **Thumbnail generation** on device (90% size reduction)
2. **WebSocket real-time notifications** (no polling needed)
3. **Smart caching strategy** (client-side thumbnail cache)

## Implementation Status

### ✅ Phase 1: Device-Side Thumbnails (COMPLETE)
**Commit:** `d258b34`

- Device generates 400x300 thumbnails at quality 85
- Typical reduction: 1MB → 50-100KB (~90% smaller)
- Backwards compatible (thumbnail optional)

**Files Changed:**
- `device/capture.py`: Added `create_thumbnail()` helper and thumbnail field to Frame
- `cloud/api/client.py`: Send thumbnail_base64 alongside full image
- `cloud/api/schemas.py`: Added thumbnail_base64 to CaptureRequest

### ✅ Phase 2: Server-Side Storage (COMPLETE)
**Commits:** `f5b4de6`, `40cdda7`

- Thumbnails stored as `{record_id}_thumb.jpeg`
- Metadata tracks thumbnail availability
- WebSocket endpoint for real-time push notifications
- Thumbnail serving endpoint with 1-day cache headers

**Files Changed:**
- `cloud/datalake/storage.py`: Store thumbnails, track in metadata
- `cloud/api/service.py`: Decode and pass thumbnails to datalake
- `cloud/api/server.py`: Add WebSocket `/ws/captures` and GET `/v1/captures/{record_id}/thumbnail`

### 🚧 Phase 3: Dashboard Updates (IN PROGRESS)

**TODO:**
1. Replace EventSource with WebSocket connection
2. Use thumbnails for grid/list view
3. Implement IndexedDB caching for thumbnails
4. Lazy load full images on demand (click/zoom)

## API Endpoints

### WebSocket: Real-Time Notifications
```javascript
// Connect to WebSocket
const ws = new WebSocket('ws://server/ws/captures?device_id=all');

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  // {event: "capture", device_id: "...", record_id: "...", state: "normal", captured_at: "..."}

  // Fetch thumbnail immediately
  fetchThumbnail(data.record_id);
};
```

### GET Thumbnail
```
GET /v1/captures/{record_id}/thumbnail
```

**Response:**
- Content-Type: `image/jpeg`
- Cache-Control: `public, max-age=86400`
- Returns thumbnail image bytes (50-100KB typically)

## Performance Improvements

### Before (Current main branch):
- Full images loaded on every refresh
- Polling every 5 seconds for new captures
- 1MB+ per image load
- Slow initial page load
- High bandwidth usage

### After (This feature branch):
- Thumbnails loaded first (100KB)
- Real-time WebSocket push (no polling)
- Full images only on demand
- Fast initial load
- 90% bandwidth reduction for grid views

## Storage Structure

```
datalake/
├── 2025/
│   ├── 01/
│   │   ├── 22/
│   │   │   ├── device-id_20250122T123456789012Z_abc123.jpeg       # Full image
│   │   │   ├── device-id_20250122T123456789012Z_abc123_thumb.jpeg # Thumbnail
│   │   │   └── device-id_20250122T123456789012Z_abc123.json       # Metadata
```

**Metadata includes:**
```json
{
  "record_id": "device-id_20250122T123456789012Z_abc123",
  "image_stored": true,
  "image_filename": "device-id_20250122T123456789012Z_abc123.jpeg",
  "thumbnail_stored": true,
  "thumbnail_filename": "device-id_20250122T123456789012Z_abc123_thumb.jpeg",
  ...
}
```

## Client-Side Caching Strategy (TODO)

### IndexedDB Cache
```javascript
// Cache structure
const thumbnailCache = {
  'record-id-1': {blob: Blob, timestamp: Date, etag: 'hash'},
  'record-id-2': {blob: Blob, timestamp: Date, etag: 'hash'}
};

// Cache thumbnails for 24 hours
// Check If-None-Match before re-fetching
// Clear entries older than 24 hours
```

### Lazy Loading
```javascript
// Initially load thumbnails
for (const record of captures) {
  img.src = getCachedThumbnail(record.record_id);
}

// Load full image on click
img.addEventListener('click', () => {
  loadFullImage(record.record_id);
});
```

## Testing

### Test Device-Side Generation
```bash
# On Raspberry Pi
cd ~/okmonitor
python -m device.main

# Check logs for thumbnail generation
# Thumbnails should be ~10% size of full images
```

### Test Server Storage
```bash
# Check datalake structure
ls -lh /mnt/data/datalake/2025/01/22/

# Should see both .jpeg and _thumb.jpeg files
# Thumbnails should be much smaller
```

### Test WebSocket
```bash
# Install websocat
npm install -g wscat

# Connect to WebSocket
wscat -c 'ws://localhost:8000/ws/captures?device_id=all'

# Should see: {"event": "connected", "target": "__all__"}
# Send test capture, should receive notification
```

### Test Thumbnail Endpoint
```bash
# Get a record_id from datalake
RECORD_ID="device-id_20250122T123456789012Z_abc123"

# Fetch thumbnail
curl -I "http://localhost:8000/v1/captures/$RECORD_ID/thumbnail"

# Should return 200 with Cache-Control headers
# Download thumbnail
curl "http://localhost:8000/v1/captures/$RECORD_ID/thumbnail" > thumb.jpeg
```

## Backward Compatibility

- ✅ Devices without thumbnail support still work
- ✅ Old captures without thumbnails still display
- ✅ Dashboard falls back to full images if thumbnail missing
- ✅ Existing API contracts unchanged

## Future Enhancements

1. **Progressive JPEG**: Use progressive encoding for better streaming
2. **WebP format**: Modern format with better compression
3. **Multiple thumbnail sizes**: Small (grid), Medium (preview), Large (lightbox)
4. **Service Worker**: Offline thumbnail caching
5. **Image CDN**: Serve thumbnails via CDN for global performance

## Rollout Plan

1. ✅ Merge feature branch to main
2. Deploy server with new endpoints
3. Update devices with new firmware (includes thumbnail generation)
4. Test with small subset of devices
5. Roll out to all devices
6. Monitor bandwidth savings and performance metrics

## Metrics to Track

- Thumbnail generation time (device)
- Thumbnail file sizes vs full images
- WebSocket connection stability
- Dashboard initial load time
- Network bandwidth usage
- Cache hit rates (when implemented)

---

**Status:** Ready for testing and Phase 3 dashboard implementation
**Branch:** `feature/optimize-image-loading`
**Next:** Implement dashboard WebSocket client and caching
