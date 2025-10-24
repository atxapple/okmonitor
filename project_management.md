# OK Monitor - Project Management Log

_Last updated: 23 October 2025_

---

## Snapshot

| Area | Status | Notes |
| --- | --- | --- |
| Device harness | Stable | Scheduled capture loop, resilient manual-trigger SSE listener, stub/real camera paths, thumbnail generation. |
| Cloud service | Stable | FastAPI app with OpenAI/Gemini consensus, JSON configuration, filesystem datalake with automatic pruning, similarity detection, thumbnail serving, WebSocket real-time updates. |
| Dashboard | Stable | Normal-description editor, trigger controls, capture gallery with real-time WebSocket updates, optimized thumbnail loading, email notification management. |
| Email alerts | Stable | SendGrid integration for automatic abnormal capture notifications. |
| Datalake pruning | Stable | Automatic disk space management for Railway deployments (3-day retention). |
| Deployment | Stable | Railway deployment with JSON config, persistent volume, automatic pruning. |
| QA / Testing | In progress | Unit tests for consensus, UI routes, AI clients; add integration smoke and load checks. |
| Security | Not started | No auth yet; relying on secret URLs and network isolation. |

---

## TODO

1. ✅ ~~"Send email" feature needs to be added~~ **COMPLETED**
   - ✅ Email alerts implemented via SendGrid
   - ✅ Links to web UI included in emails
   - ⚠️ Shortest interval still needs to be set as 10 mins (configurable in device settings)
2. Make the cloud and device run stably for at least one week without stopping.
   - Add exponential backoff and logging to the SSE reconnect loop (`device.main`).
   - Capture and archive logs for the burn-in run.
   - Add automated regression covering manual-trigger counter resets after reconnect.
3. Implement WiFi setup by AP function.
4. ✅ ~~Draft deployment script~~ **COMPLETED** - JSON config simplifies deployment
5. Evaluate lightweight auth strategy (shared API token vs. signed requests) and implement a POC.
6. ✅ ~~Document the normal-description workflow in README~~ **COMPLETED**
7. ✅ ~~If the image has no difference, then do not use AI~~ **COMPLETED** - Similarity detection implemented
8. ⚠️ Compare the speed of inference at the cloud or at the device. Then choose a better one. (Currently cloud-only)
9. ✅ ~~Show uploaded image immediately~~ **COMPLETED** - Real-time WebSocket updates implemented
   - ⚠️ Pending-state UX still needed (show "classifying..." status)

---

## Recent Wins

- **JSON Configuration**: Replaced 30+ CLI flags with clean `config/cloud.json` file, simplifying Railway deployment
- **Datalake Pruning**: Automatic disk space management deletes old normal/uncertain full images while preserving thumbnails, metadata, and all abnormal captures
- **Email Notifications**: SendGrid integration sends automatic alerts with links to web UI when abnormal captures detected
- **Real-Time Updates**: WebSocket implementation replaces polling for instant dashboard updates
- **Thumbnail Optimization**: Device generates thumbnails (~90% size reduction), server stores and serves them with cache headers
- **Similarity Detection**: Perceptual hashing skips AI inference for duplicate frames, saving API costs
- **Streak Pruning**: Optional feature to reduce storage during long periods of identical states
- Manual triggers survive API restarts thanks to the counter reset fix, so operators don't lose the first capture after reconnect
- `RecentCaptureIndex` keeps the gallery responsive even with large capture sets
- Normal-description edits now cascade to nested classifiers, removing stale prompts
- Consensus labels render as `Agent1` / `Agent2` in the UI while server logs retain real provider names
- Railway deployment uses `/mnt/data` volume for guidance files and the datalake
- Device-supplied timestamps now drive capture filenames and UI display, with cloud ingest time kept as a tooltip for drift debugging

---

## Watchouts

| Risk | Impact | Mitigation |
| --- | --- | --- |
| Vendor API limits (OpenAI/Gemini) | 429s on classification calls | Rate-limit on device, queue retries with debounce, add single-agent fallback. |
| Filesystem datalake durability | Capture loss on local disk failure | Move to object storage (S3/MinIO) with scheduled backups and DB metadata. |
| Lack of auth | Unauthorized uploads/config changes | Ship API tokens and dashboard login before pilot deployment. |
| SSE idle timeouts (Railway) | Manual-trigger listener churn | Increase server read timeout, add keep-alive heartbeats, and implement reconnect backoff (pending). |

---

## Reference

- Tests: `python -m unittest discover tests`
- Device smoke test: `python -m device.main --camera stub --camera-source samples/test.jpg --api http --api-url http://127.0.0.1:8000 --iterations 3 --verbose`
- Railway deployment:
  ```bash
  # Start command (simplified!)
  python -m cloud.api.main

  # Configuration loaded from config/cloud.json
  # Secrets set as environment variables:
  # - OPENAI_API_KEY
  # - GEMINI_API_KEY
  # - SENDGRID_API_KEY (optional)
  # - ALERT_FROM_EMAIL (optional)
  ```
- Local development:
  ```bash
  # 1. Copy config files
  cp .env.example .env
  cp config/cloud.example.json config/cloud.json

  # 2. Configure secrets in .env

  # 3. Start server
  python -m cloud.api.main
  ```
