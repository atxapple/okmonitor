# OK Monitor Architecture Overview (October 2025)

> **Vision:** Deliver a snap-to-cloud inspection loop where a lightweight device captures frames, the cloud classifies them with multiple AI agents, and operators close the loop via a web dashboard.

---

## MVP Deliverables

- **Single-device harness** that schedules captures, listens for SSE/manual triggers, polls configuration, and uploads frames with actuator logging.
- **Cloud consensus service** exposing capture ingestion, configuration, and manual trigger endpoints while maintaining an in-memory capture index and device presence metadata.
- **Web dashboard** for managing trigger cadence, editing the normal-description prompt, firing manual captures, and browsing filtered capture history with live status feedback and real-time WebSocket updates.
- **Email notification system** for automatic alerts when anomalies are detected.
- **Datalake pruning** for automatic disk space management on Railway deployments.
- **Image optimization** with thumbnail generation and WebSocket real-time updates.
- **Deployment scripts** covering local development and Railway hosting with JSON configuration, `.env` loading, and persistent volume mounts.
- **Automated tests** exercising UI routes, API clients, and consensus logic as part of the continuous integration workflow.

---

## Out of Scope

- Multiple devices, fleet management, or OTA updates.
- Hardware GPIO integration beyond the loopback actuator stub.
- Authenticated user accounts, RBAC, or audit trails.
- Advanced analytics beyond basic capture classification.
- Automated model retraining or label ingestion outside of normal-description edits.

---

## Acceptance Criteria

1. End-to-end trigger -> classification -> response completes in under two seconds on a consumer laptop paired with the Railway backend.
2. The dashboard reflects normal-description edits within one refresh and persists the exact text to disk/volume storage.
3. Consensus classification responses record detailed Agent1/Agent2 reasons for abnormal or uncertain captures.
4. The device harness gracefully reconnects to the manual-trigger SSE stream when idle disconnects occur and preserves pending manual captures across reconnects.
5. `python -m unittest discover tests` passes locally and in CI.

---

## Current Snapshot

- **Device harness** (Python) runs a scheduled capture loop, listens for SSE/manual-trigger events, polls `/v1/device-config`, and uploads JPEG frames with actuator logging and optional local saves.
- **Cloud FastAPI service** ingests captures, tracks device presence, brokers manual-trigger fan-out via the trigger hub, reconciles Agent1/Agent2 outputs, generates thumbnails, sends email alerts for abnormal captures, and stores artifacts in the filesystem datalake with automatic pruning.
- **Web dashboard** surfaces live device status with real-time WebSocket updates, offers trigger and manual controls, presents a filterable capture gallery with optimized thumbnail loading, and provides notification settings management.
- **Email notifications** via SendGrid automatically alert recipients when abnormal captures are detected.
- **Datalake pruning** automatically deletes old normal/uncertain full-size images while preserving thumbnails, metadata, and all abnormal captures.
- **Configuration** centralized in `config/cloud.json` with secrets in `.env`.
- **Deployment targets** include local development and Railway with a persistent volume at `/mnt/data` for configuration plus datalake storage.

---

## System Architecture

### Device Runtime (`device/`)

| Module | Responsibility |
| --- | --- |
| `device.main` | CLI entrypoint providing the scheduled capture loop, SSE/manual-trigger listener, config polling, and graceful shutdown. |
| `device.harness` | Runs the trigger -> capture -> upload -> actuation pipeline. |
| `device.capture` | Wraps OpenCV (or stub image) to provide frames. |
| `device.trigger` | Simple software queue used by scheduler, manual triggers, and tests. |
| `cloud.api.client` | HTTP client for `POST /v1/captures`, with timeout handling and verbose error reporting. |

**Trigger sources**
- Recurring interval stored in cloud config (`/v1/device-config`).
- Manual trigger SSE stream (`/v1/manual-trigger/stream`).
- CLI/demo injection during dry runs.

### Cloud Runtime (`cloud/`)

| Component | Responsibility |
| --- | --- |
| `cloud.api.main` | CLI for loading JSON config and `.env`, resolving normal-description path, starting uvicorn with periodic pruning task. |
| `cloud.api.config_loader` | Loads configuration from `config/cloud.json` with environment variable overrides. |
| `cloud.api.server` | Builds FastAPI app, wires datalake, capture index, classifiers, manual-trigger hub, device status tracking, web routes, thumbnail generation, and WebSocket broadcast. |
| `cloud.ai.openai_client` (Agent1) | Calls OpenAI `gpt-4o-mini` with JSON structured responses. |
| `cloud.ai.gemini_client` (Agent2) | Calls Google Gemini 2.5 Flash via REST, with logging and error surfacing. |
| `cloud.ai.consensus` | Reconciles Agent1/Agent2 decisions, flagging low confidence or disagreement as `uncertain` and labelling responses with `Agent1` / `Agent2`. |
| `cloud.datalake.storage` | Stores JPEG, thumbnail, and JSON metadata under `datalake/YYYY/MM/DD` with similarity detection and streak pruning. |
| `cloud.api.capture_index` | Maintains the capture index pipeline that feeds recent capture summaries to the dashboard. |
| `cloud.api.email_service` | SendGrid integration for abnormal capture email alerts. |
| `cloud.api.datalake_pruner` | Periodic background task that deletes old normal/uncertain full-size images. |
| `cloud.web.routes` | Dashboard API: state, captures, trigger config, normal-description persistence, notification settings, and thumbnail endpoint. |
| `cloud.web.capture_utils` | Shared helpers to parse capture JSON and find paired images. |

### Dashboard (`cloud/web/templates/index.html`)

- Live status indicator showing device presence/heartbeat state with real-time WebSocket updates.
- Normal-condition editor that persists to disk and updates all classifiers (consensus plus agents).
- Trigger panel (enable/disable, interval, manual trigger button) plus manual-trigger feedback messaging.
- Notification settings (email alerts with recipient management, enable/disable toggle).
- Capture gallery with filters (state, date range, limit), real-time updates via WebSocket, optimized thumbnail loading, and download icons.

---

## Data Flow

1. Device polls `/v1/device-config` for trigger enablement, interval, manual-trigger counter, and normal-description updates while updating device-last-seen metadata server-side.
2. Scheduler enqueues triggers (`schedule-<epoch>`) or processes manual/SSE events (`manual-<epoch>-<counter>`) before capturing frames via OpenCV (or stub image).
3. Captures can be mirrored to `debug_captures/` for troubleshooting and then uploaded through `cloud.api.client` to `/v1/captures` with metadata (device ID, trigger label).
4. FastAPI service processes the capture:
   - Checks similarity cache to skip duplicate classifications
   - Records device status
   - Runs Agent1 and Agent2 (or single classifier based on config)
   - Merges results via consensus
   - Generates thumbnail
   - Stores full image, thumbnail, and JSON metadata in datalake
   - Broadcasts capture event via WebSocket
   - Sends email alert if abnormal and notifications enabled
5. Manual triggers initiated from the dashboard increment the server counter, fan out through the trigger hub, and surface to the device SSE listener; counter resets during reconnects now enqueue the pending capture automatically.
6. The device receives the inference response (state, confidence, reason, record_id) and logs actuator state transitions.
7. The dashboard receives real-time updates via WebSocket when new captures arrive.
8. Background pruning task runs every 24 hours to delete old normal/uncertain full-size images while preserving thumbnails, metadata, and all abnormal captures.

---

## Deployment Notes

- **Local development**
  ```bash
  # 1. Copy config files
  cp .env.example .env
  cp config/cloud.example.json config/cloud.json

  # 2. Configure secrets in .env
  # OPENAI_API_KEY=...
  # GEMINI_API_KEY=...
  # SENDGRID_API_KEY=... (optional)
  # ALERT_FROM_EMAIL=... (optional)

  # 3. Start server
  python -m cloud.api.main
  ```
  Configuration is loaded from `config/cloud.json`. CLI arguments can override config file settings.

- **Railway**
  ```bash
  python -m cloud.api.main
  ```
  - Set environment variables in Railway dashboard: `OPENAI_API_KEY`, `GEMINI_API_KEY`, `SENDGRID_API_KEY` (optional), `ALERT_FROM_EMAIL` (optional)
  - Configuration is loaded from `config/cloud.json` in the repository
  - Mount persistent volume at `/mnt/data` for datalake and runtime config
  - Datalake pruning automatically manages disk space (3-day retention by default)

---

## Repository Map (2025-09)

- `cloud/ai/`  Agent1, Agent2, consensus logic
- `cloud/api/`  FastAPI app, capture index, service orchestration
- `cloud/datalake/`  Filesystem storage helpers
- `cloud/web/`  Dashboard routes and template
- `device/`  Capture, trigger, and upload harness
- `config/`  Example normal-description files used in docs/demo
- `samples/`  Test images for stub camera
- `tests/`  Unit tests (consensus, UI routes, AI clients)
- `README.md`  Getting started guide

---

## Testing and Quality

- `python -m unittest discover tests` runs the full suite (consensus, UI routes, AI clients).
- Device harness can be smoke-tested with the stub camera:
  ```bash
  python -m device.main --camera stub --camera-source samples/test.jpg --api http --api-url http://127.0.0.1:8000 --iterations 3
  ```
- Logging is verbose for classifier calls (`cloud.ai.*`), making remote diagnosis easier in Railway logs.

---

## Post-MVP Roadmap

1. **Authentication and security** - Add API tokens for device-to-cloud communication and secure the dashboard.
2. **Multi-tenant SaaS** - PostgreSQL database, JWT authentication, user accounts, device pairing (see `future/multi-tenant-saas` branch).
3. **Hardware GPIO integration** - Wire digital output toggles to real hardware adapters.
4. **Observability** - Export metrics (trigger cadence, classification latency, agent disagreement rates).
5. **Fleet features** - Multi-device registry, health heartbeat, and remote configuration bundles.
6. **Model lifecycle** - Replace vendor APIs with managed fine-tuned models or on-prem inference when available.
