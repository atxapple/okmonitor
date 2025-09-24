# OK Monitor – MVP Scope (September 2025)

> Deliver a demo-ready inspection loop that captures frames on a schedule, classifies them with consensus AI in the cloud, and lets operators tweak “normal” context through a web dashboard.

---

## Included in the MVP

- **Single device harness** (Windows/Linux laptop or NUC) with:
  - Recurring trigger scheduler + SSE listener for manual triggers
  - OpenCV camera capture or stub image source
  - Upload pipeline to `POST /v1/captures` and actuator logging
- **Cloud FastAPI service** with:
  - Agent1 (OpenAI `gpt-4o-mini`) + Agent2 (Gemini 2.5 Pro) classifiers
  - Consensus reconciliation + logging + capture index
  - Filesystem datalake storing JPEG + JSON per capture
  - REST endpoints powering the device and dashboard
- **Web dashboard** providing:
  - Normal-description editor (persisted to disk + pushed to agents)
  - Trigger controls (interval, manual trigger, auto refresh)
  - Recent capture gallery with filtering + download
- **Local & Railway deployment scripts** using `.env` and volume-mounted guidance files
- **Automated tests** for UI routes, consensus logic, and API clients

---

## Out of Scope for MVP

- Multiple devices / fleet management / OTA updates
- Hardware GPIO integration (DI/DO) beyond the software actuator stub
- Authenticated user accounts, RBAC, audit logs
- Advanced analytics, alerting, or notification delivery
- Automated model retraining or label ingestion beyond normal-description updates

---

## Architecture Summary

```
(Device)             (Cloud)
trigger -> capture -> upload  ---> FastAPI -> Agent1/Agent2 -> consensus -> datalake
          ^ SSE stream ------------------- dashboard (UI) ---------------------/
```

- Device polls `/v1/device-config` to stay in sync with normal description + interval
- Edited descriptions are written to `/mnt/data/config/normal_guidance.txt` (or local path) and immediately applied to both agents
- Capture index provides fast gallery loads without scanning the datalake each refresh

---

## Acceptance Criteria

1. End-to-end trigger -> classification -> response completes in < 2 seconds on a consumer laptop + Railway backend
2. UI reflects updated normal description within one refresh, and the file on disk stores the same text
3. Consensus classifier records detailed reasons (Agent1/Agent2) for abnormal/uncertain captures
4. Device harness gracefully reconnects to manual-trigger SSE when Railway idles the connection
5. `python -m unittest discover tests` passes locally and in CI

---

## Next-Step Enhancements (Post-MVP)

1. Add device authentication + signed configuration updates
2. Implement notification delivery (email/Slack) and hardware output adapters
3. Support multiple devices and centralized configuration management
4. Persist metadata in a database (PostgreSQL/S3) for durability beyond a single host
5. Introduce human labeling workflow and model fine-tuning automation
