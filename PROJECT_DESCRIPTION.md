# OK Monitor Architecture Overview (September 2025)

> **Vision:** Deliver a snap-to-cloud inspection loop where a lightweight device captures frames, the cloud classifies them with multiple AI agents, and operators close the loop via a web dashboard.

---

## Current Snapshot

- **Device harness** (Python) schedules captures, listens for manual triggers over SSE, and uploads JPEG frames with metadata.
- **Cloud FastAPI service** accepts captures, runs Agent1 (OpenAI) and Agent2 (Gemini) models, reconciles results with a consensus classifier, and stores artifacts in a filesystem datalake.
- **Web dashboard** lets operators edit the "normal" guidance, tune the recurring trigger interval, fire manual triggers, and review/download recent captures.
- **Deployment targets** include local development and Railway with a persistent volume at `/mnt/data` for configuration plus datalake storage.

---

## System Architecture

### Device Runtime (`device/`)

| Module | Responsibility |
| --- | --- |
| `device.main` | CLI entrypoint providing schedule loop, SSE listener, and graceful shutdown. |
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
| `cloud.api.server` | Builds FastAPI app, wires datalake, capture index, classifiers, and web routes. |
| `cloud.ai.openai_client` (Agent1) | Calls OpenAI `gpt-4o-mini` with JSON structured responses. |
| `cloud.ai.gemini_client` (Agent2) | Calls Google Gemini 2.5 Pro via REST, with logging and error surfacing. |
| `cloud.ai.consensus` | Reconciles Agent1/Agent2 decisions, flagging low confidence or disagreement as `uncertain` and labelling responses with `Agent1` / `Agent2`. |
| `cloud.datalake.storage` | Stores JPEG plus JSON metadata under `cloud_datalake/YYYY/MM/DD`. |
| `cloud.api.capture_index` | Keeps an in-memory LRU index so the UI can show latest captures without walking the filesystem. |
| `cloud.web.routes` | Dashboard API: state, captures, trigger config, and normal-description persistence. |
| `cloud.web.capture_utils` | Shared helpers to parse capture JSON and find paired images. |

### Dashboard (`cloud/web/templates/index.html`)

- "Normal Condition" editor that persists to disk and updates every nested classifier (consensus plus agents).
- Trigger panel (enable/disable, interval, manual trigger button).
- Notification placeholders (email/digital output toggles recorded for future features).
- Capture gallery with filters (state, date range, limit), auto-refresh toggle, and download icons.

---

## Data Flow

1. Device polls `/v1/device-config` to obtain schedule interval and current normal description.
2. Scheduler enqueues triggers (`schedule-<epoch>`) and the harness captures a frame via OpenCV (or stub image).
3. Capture is optionally written to `debug_captures/` for troubleshooting.
4. `cloud.api.client` posts to `/v1/captures` with base64 JPEG plus metadata (device, trigger label).
5. FastAPI service runs Agent1 and Agent2, logs results, merges via consensus, and stores the outcome in the datalake plus capture index.
6. Response returns to the device (state, confidence, reason, record_id); harness logs and toggles the actuator stub.
7. Dashboard polls `/ui/captures` to refresh the gallery. Editing the guidance triggers `_apply_normal_description`, pushing the updated string into every classifier and writing the file to disk/volume.

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

- `cloud/ai/` – Agent1, Agent2, consensus logic
- `cloud/api/` – FastAPI app, capture index, service orchestration
- `cloud/datalake/` – Filesystem storage helpers
- `cloud/web/` – Dashboard routes and template
- `device/` – Capture, trigger, and upload harness
- `config/` – Example normal-description files used in docs/demo
- `samples/` – Test images for stub camera
- `tests/` – Unit tests (consensus, UI routes, AI clients)
- `README.md` – Getting started guide

---

## Testing and Quality

- `python -m unittest discover tests` runs the full suite (consensus, UI routes, AI clients).
- Device harness can be smoke-tested with the stub camera:
  ```bash
  python -m device.main --camera stub --camera-source samples/test.jpg --api http --api-url http://127.0.0.1:8000 --iterations 3
  ```
- Logging is verbose for classifier calls (`cloud.ai.*`), making remote diagnosis easier in Railway logs.

---

## Roadmap Highlights

1. **Authentication and security** - Add API tokens for device-to-cloud communication and secure the dashboard.
2. **Notification pipeline** - Wire email/digital output toggles to real services and hardware adapters.
3. **Observability** - Export metrics (trigger cadence, classification latency, agent disagreement rates).
4. **Fleet features** - Device registry, health heartbeat, and remote configuration bundles.
5. **Model lifecycle** - Replace vendor APIs with managed fine-tuned models or on-prem inference when available.
