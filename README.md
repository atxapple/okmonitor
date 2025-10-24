# OK Monitor

AI-powered visual monitoring system for detecting environmental anomalies through continuous camera surveillance.

## Quick Start

### 1. Environment Setup

Copy `.env.example` to `.env` and configure your API keys:

```bash
cp .env.example .env
```

Required secrets in `.env`:
```env
# AI Classifier API Keys
OPENAI_API_KEY=your-openai-api-key
GEMINI_API_KEY=your-gemini-api-key

# Email Notifications (optional)
SENDGRID_API_KEY=your-sendgrid-key
ALERT_FROM_EMAIL=alerts@example.com
```

### 2. Server Configuration

Copy `config/cloud.example.json` to `config/cloud.json`:

```bash
cp config/cloud.example.json config/cloud.json
```

All server configuration is now in `config/cloud.json`. See [Configuration](#configuration) section below for details.

### 3. Start the Server

```bash
python -m cloud.api.main
```

The server will:
- Load configuration from `config/cloud.json`
- Load secrets from `.env`
- Start API server on `http://localhost:8000`
- Web dashboard available at `http://localhost:8000/ui`

## Configuration

All configuration is managed through `config/cloud.json`. Secrets (API keys) go in `.env`.

### Configuration Structure

```json
{
  "server": {
    "host": "0.0.0.0",
    "port": 8000
  },
  "storage": {
    "datalake_root": "/mnt/data/datalake"
  },
  "classifier": {
    "backend": "consensus",  // or "openai", "gemini", "simple"
    "openai": {
      "model": "gpt-4o-mini",
      "timeout": 30.0
    },
    "gemini": {
      "model": "models/gemini-2.5-flash",
      "timeout": 30.0
    }
  },
  "features": {
    "similarity": {
      "enabled": true,
      "threshold": 1,
      "expiry_minutes": 3.0
    },
    "datalake_pruning": {
      "enabled": true,
      "retention_days": 3,
      "run_on_startup": true,
      "run_interval_hours": 24
    }
  }
}
```

See `config/cloud.example.json` for full configuration options.

## Features

### AI Classification

Captures are classified as:
- **normal**: Matches expected environment description
- **abnormal**: Anomaly detected with AI-generated reason
- **uncertain**: Low model confidence or classifier disagreement

Supports multiple AI backends:
- **OpenAI** (GPT-4o-mini)
- **Gemini** (Gemini 2.5 Flash)
- **Consensus** (uses both for higher accuracy)
- **Simple** (threshold-based, no AI)

### Web Dashboard

Access at `http://localhost:8000/ui`:
- Update "normal" environment description
- Configure capture intervals
- Review captured images with AI classifications
- Manage email notification settings
- Real-time WebSocket updates (no polling!)
- Optimized thumbnail loading

### Email Alerts

Automatic email notifications when anomalies are detected:

1. Configure SendGrid credentials in `.env`
2. Use dashboard to add recipient emails and enable alerts
3. Settings are persisted in `/mnt/data/config/notifications.json`

### Datalake Pruning

**NEW**: Automatic disk space management for Railway deployments.

Automatically deletes old normal/uncertain full-size images while preserving:
- ✅ Thumbnails for all captures (visual reference)
- ✅ All JSON metadata (classification history)
- ✅ ALL abnormal captures completely untouched

Configuration:
```json
"datalake_pruning": {
  "enabled": true,
  "retention_days": 3,
  "run_on_startup": true,
  "run_interval_hours": 24
}
```

Manual control via admin endpoints:
- Preview: `GET /v1/admin/prune-datalake/stats`
- Run manually: `POST /v1/admin/prune-datalake?dry_run=true`

### Similarity Detection

Skips AI inference for visually identical frames:

```json
"similarity": {
  "enabled": true,
  "threshold": 1,        // Hamming distance threshold
  "expiry_minutes": 3.0  // Cache expiration
}
```

Saves AI API costs by reusing previous classifications for similar images.

### Streak Pruning

Reduces storage by not saving duplicate images during long identical periods:

```json
"streak_pruning": {
  "enabled": false,
  "threshold": 10,     // Start pruning after N identical states
  "keep_every": 5      // Keep 1 image every N captures during streak
}
```

Metadata is always preserved, only full-size images are skipped.

## Device Setup

### Raspberry Pi Device

```bash
python -m device.main \
  --camera opencv \
  --camera-source 0 \
  --api http \
  --api-url http://your-server:8000 \
  --device-id floor-01-cam \
  --iterations 0 \
  --verbose
```

Options:
- `--camera opencv`: Use OpenCV for camera capture
- `--camera stub`: Use test image instead of camera
- `--camera-source 0`: Camera device index or image path
- `--iterations 0`: Run indefinitely
- Device polls `/v1/device-config` for schedule changes

See `deployment/okmonitor-device.service` for systemd setup.

## Deploying to Railway

Railway configuration is simplified - just set environment variables!

### 1. Environment Variables

Set these in Railway dashboard:
```
OPENAI_API_KEY=your-key
GEMINI_API_KEY=your-key
SENDGRID_API_KEY=your-key (optional)
ALERT_FROM_EMAIL=alerts@example.com (optional)
OK_CLOUD_BASE_URL=https://your-app.railway.app (optional)
```

### 2. Start Command

```bash
python -m cloud.api.main
```

That's it! Configuration is loaded from `config/cloud.json` in the repo.

### 3. Persistent Volume

Railway automatically mounts `/mnt/data` for:
- Datalake: `/mnt/data/datalake`
- Config: `/mnt/data/config/`
- Normal description: `/mnt/data/config/normal_guidance.txt`
- Notifications: `/mnt/data/config/notifications.json`

## Architecture

### Single-Tenant (Current)

```
Device (Raspberry Pi)
  ↓ HTTP POST /v1/captures
Cloud Server (Railway)
  ↓ AI Classification (OpenAI/Gemini)
Datalake Storage (/mnt/data)
  + Web Dashboard (port 8000/ui)
  + Email Alerts (SendGrid)
```

- One server instance per deployment
- Devices upload captures via REST API
- WebSocket for real-time UI updates
- Automatic pruning manages disk usage

### Multi-Tenant (Future)

See `ARCHITECTURE.md` in `future/multi-tenant-saas` branch for planned SaaS architecture with:
- PostgreSQL database
- JWT authentication
- User accounts & device pairing
- Multi-user web dashboard

## Development

### Branch Strategy

- `main`: Production-ready code
- `dev`: Active development, deployed to Railway for testing
- `feature/*`: Feature branches merged to dev
- `future/*`: Future work (e.g., multi-tenant architecture)

See `DEV-BRANCH.md` for dev branch workflow.

### Testing

```bash
# Run tests
pytest

# With coverage
pytest --cov=cloud --cov=device
```

See `TESTING-GUIDE.md` for comprehensive testing documentation.

### Image Optimization Testing

See `OPTIMIZATION.md` for testing WebSocket updates, thumbnails, and real-time features.

## API Endpoints

### Device API
- `POST /v1/captures` - Submit capture for classification
- `GET /v1/device-config` - Get capture schedule
- `POST /v1/manual-trigger` - Trigger immediate capture
- `GET /v1/manual-trigger/stream` - SSE stream for triggers

### Web Dashboard
- `GET /ui` - Web dashboard interface
- `GET /v1/captures/{record_id}/thumbnail` - Optimized thumbnails
- `GET /v1/capture-events/stream` - WebSocket real-time updates

### Admin
- `GET /v1/admin/prune-datalake/stats` - Preview pruning stats (dry-run)
- `POST /v1/admin/prune-datalake` - Manually trigger pruning

## Troubleshooting

### Camera Issues

If experiencing lag or old frames:
- Camera buffer lag fix implemented (30 pre-grab frames)
- See timing debug feature in `config/cloud.json`:
  ```json
  "timing_debug": {
    "enabled": true,
    "max_captures": 100
  }
  ```

### Railway Disk Space

Enable datalake pruning in `config/cloud.json`:
```json
"datalake_pruning": {
  "enabled": true,
  "retention_days": 3
}
```

This automatically manages disk usage by deleting old normal images.

### Email Alerts Not Sending

1. Check environment variables are set in Railway
2. Verify SendGrid API key is valid
3. Check notification settings in dashboard
4. Review server logs for email service errors

## License

[Your License Here]

## Contributing

[Your Contributing Guidelines Here]
