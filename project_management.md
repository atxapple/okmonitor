# OK Monitor - Project Management Log

_Last updated: 24 September 2025_

---

## Current Status

| Area | Status | Notes |
| --- | --- | --- |
| Device harness | Complete | Scheduled capture loop, SSE manual trigger listener, OpenCV/stub cameras, upload plus actuator logging. |
| Cloud service | Complete | FastAPI app with Agent1 (OpenAI) + Agent2 (Gemini) consensus, filesystem datalake, capture index, logging. |
| Dashboard | Complete | Normal-description editor (propagates to all agents), trigger controls, capture gallery with filters/download, auto-refresh guard. |
| Deployment | In progress | Local runbook solid; Railway deployment tested with `/mnt/data` volume. Need scripted provisioning and monitoring setup. |
| QA / Testing | In progress | Unit tests cover consensus, UI routes, AI clients. Need integration smoke tests (device <-> cloud) and load checks. |
| Security | Pending | No auth yet; relies on secret URLs plus network isolation. |

---

## Recent Highlights (Sprint 9)

- Added `RecentCaptureIndex` so the gallery loads instantly even with thousands of captures.
- Normal-description updates now propagate to nested classifiers, fixing stale prompts after edits.
- Consensus labels anonymised to `Agent1` / `Agent2` for UI while still logging real providers server-side.
- Railway deployment hardened: start command uses `/mnt/data` volume for guidance plus datalake; manual-trigger stream timeout guidance documented.

---

## Active Work

1. **Deployment automation** - Write Railway/Compose scripts to provision secrets, volumes, and health checks.
2. **Resilience** - Add exponential backoff to manual-trigger SSE reconnects and capture uploads.
3. **Documentation refresh** - Update README with local and Railway runbooks, API endpoint reference, and troubleshooting tips.

---

## Backlog / Upcoming Milestones

### Short Term (1-2 sprints)
- Implement API token authentication for device endpoints.
- Wire notification settings to a simple email webhook (SendGrid/Mailgun).
- Add integration smoke test (device stub <-> local cloud) in CI.

### Mid Term (3-4 sprints)
- Persist metadata in SQLite/PostgreSQL rather than relying solely on filesystem lookups.
- Introduce device registry plus heartbeat for multi-device support.
- Surface agent disagreement metrics and latency stats in the dashboard.

### Long Term
- Pluggable notification channels (Slack, Teams, Webhooks).
- Hardware GPIO adapters for DI/DO boards and documented wiring guides.
- Model lifecycle tooling (label review, fine-tuning pipeline, version promotion).

---

## Risks & Mitigations

| Risk | Impact | Mitigation |
| --- | --- | --- |
| Vendor API limits (OpenAI/Gemini) | Classifier returns 429 -> device sees errors | Rate-limit on device, implement queued retry plus local debounce, support single-agent fallback. |
| Filesystem datalake durability | Loss of local disk or Railway volume wipes captures | Move to object storage (S3/MinIO) and DB metadata; scheduled backup job. |
| No auth on endpoints | Unauthorized uploads or config changes | Add API tokens and dashboard login before pilot deployment. |
| SSE idle timeouts (Railway) | Manual-trigger listener reconnect churn | Increase read timeout (configurable) plus keep-alive heartbeats server-side. |

---

## Next Concrete Steps

1. Draft deployment script (Makefile or PowerShell) to spin up local cloud plus stub device.
2. Add exponential backoff and logging to SSE reconnect loop (`device.main`).
3. Document normal-description workflow in README (including Docker/Railway path notes).
4. Evaluate lightweight auth strategy (shared API token vs. signed requests) and implement POC.

---

## Stakeholders & Communication

- **Product / Ops**: Weekly checkpoint reviewing dashboard output and classifier behaviour.
- **Engineering**: Async updates in repo README and project board; PRs must include test evidence.
- **External vendors**: Track API usage thresholds (OpenAI/Gemini) and rotate keys before limits hit.

---

## Appendix

- Unit tests: `python -m unittest discover tests`
- Device smoke test: `python -m device.main --camera stub --camera-source samples/test.jpg --api http --api-url http://127.0.0.1:8000 --iterations 3 --verbose`
- Railway start command:
  ```bash
  python -m cloud.api.main \
    --classifier consensus \
    --normal-description-path /mnt/data/config/normal_guidance.txt \
    --datalake-root /mnt/data/datalake
  ```
