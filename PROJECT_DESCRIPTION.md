# OK Monitor Architecture Overview (October 2025)

> **Vision:** Deliver a snap-to-cloud inspection loop where a lightweight device captures frames, the cloud classifies them with multiple AI agents, and operators close the loop via a web dashboard.

---

## MVP Deliverables

- **Single-device harness** that schedules captures, listens for SSE/manual triggers, polls configuration, and uploads frames with actuator logging.
- **Cloud consensus service** exposing capture ingestion, configuration, and manual trigger endpoints while maintaining an in-memory capture index and device presence metadata.
- **Web dashboard** for managing trigger cadence, editing the normal-description prompt, firing manual captures, and browsing filtered capture history with live status feedback.
- **Deployment scripts** covering local development and Railway hosting with `.env` loading and persistent volume mounts for configuration plus datalake storage.
- **Automated tests** exercising UI routes, API clients, and consensus logic as part of the continuous integration workflow.

---

## Out of Scope

- Multiple devices, fleet management, or OTA updates.
- Hardware GPIO integration beyond the loopback actuator stub.
- Authenticated user accounts, RBAC, or audit trails.
- Advanced analytics, alerting pipelines, or notification delivery mechanisms.
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
- **Cloud FastAPI service** ingests captures, tracks device presence, brokers manual-trigger fan-out via the trigger hub, reconciles Agent1/Agent2 outputs, and stores artifacts plus index entries in the filesystem datalake (including metadata-only streak entries).
- **Web dashboard** surfaces live device status, offers trigger and manual controls, and presents a filterable capture gallery with state/date/limit inputs alongside normal-description editing and metadata-only streak rows.
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
| `cloud.api.main` | CLI for loading `.env`, resolving normal-description path, starting uvicorn. |
| `cloud.api.server` | Builds FastAPI app, wires datalake, capture index, classifiers, manual-trigger hub, device status tracking, and web routes (including `/v1/device-config`). |
| `cloud.ai.openai_client` (Agent1) | Calls OpenAI `gpt-4o-mini` with JSON structured responses. |
| `cloud.ai.gemini_client` (Agent2) | Calls Google Gemini 2.5 Pro via REST, with logging and error surfacing. |
| `cloud.ai.consensus` | Reconciles Agent1/Agent2 decisions, flagging low confidence or disagreement as `uncertain` and labelling responses with `Agent1` / `Agent2`. |
| `cloud.datalake.storage` | Stores JPEG plus JSON metadata under `cloud_datalake/YYYY/MM/DD`. |
| `cloud.api.capture_index` | Maintains the capture index pipeline that feeds recent capture summaries to the dashboard. |
| `cloud.web.routes` | Dashboard API: state, captures, trigger config, and normal-description persistence. |
| `cloud.web.capture_utils` | Shared helpers to parse capture JSON and find paired images. |

### Dashboard (`cloud/web/templates/index.html`)

- Live status indicator showing device presence/heartbeat state.
- Normal-condition editor that persists to disk and updates all classifiers (consensus plus agents).
- Trigger panel (enable/disable, interval, manual trigger button) plus manual-trigger feedback messaging.
- Notification placeholders (email/digital output toggles recorded for future features).
- Capture gallery with filters (state, date range, limit), auto-refresh toggle, and download icons.

---

## Data Flow

1. Device polls `/v1/device-config` for trigger enablement, interval, manual-trigger counter, and normal-description updates while updating device-last-seen metadata server-side.
2. Scheduler enqueues triggers (`schedule-<epoch>`) or processes manual/SSE events (`manual-<epoch>-<counter>`) before capturing frames via OpenCV (or stub image).
3. Captures can be mirrored to `debug_captures/` for troubleshooting and then uploaded through `cloud.api.client` to `/v1/captures` with metadata (device ID, trigger label).
4. FastAPI service processes the capture, records device status, runs Agent1 and Agent2, merges the results via consensus, and writes the datalake artifact plus capture index entry.
5. Manual triggers initiated from the dashboard increment the server counter, fan out through the trigger hub, and surface to the device SSE listener; counter resets during reconnects now enqueue the pending capture automatically.
6. The device receives the inference response (state, confidence, reason, record_id) and logs actuator state transitions.
7. The capture gallery reflects each ingestion, including metadata-only streak entries when JPEG pruning is active.
7. Dashboard polling retrieves `/ui/state` and `/ui/captures` for live status indicators, trigger settings, and gallery refresh with applied filters.

---

## Deployment Notes

- **Local development**
  ```bash
  python -m cloud.api.main \
    --classifier consensus \
    --normal-description-path config/normal_guidance.txt \
    --datalake-root cloud_datalake
  ```
- **Railway**
  ```bash
  python -m cloud.api.main \
    --classifier consensus \
    --normal-description-path /mnt/data/config/normal_guidance.txt \
    --datalake-root /mnt/data/datalake
  ```
  Provide `OPENAI_API_KEY` and `GEMINI_API_KEY` as Railway secrets and mount a volume at `/mnt/data`.
- `.env` is consumed via `dotenv` before environment variables, so local overrides are simple.

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
2. **Notification pipeline** - Wire email/digital output toggles to real services and hardware adapters.
3. **Observability** - Export metrics (trigger cadence, classification latency, agent disagreement rates).
4. **Fleet features** - Device registry, health heartbeat, and remote configuration bundles.
5. **Model lifecycle** - Replace vendor APIs with managed fine-tuned models or on-prem inference when available.
