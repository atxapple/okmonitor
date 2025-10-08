# OK Monitor - Project Management Log

_Last updated: 28 September 2025_

---

## Snapshot

| Area | Status | Notes |
| --- | --- | --- |
| Device harness | Stable | Scheduled capture loop, manual-trigger SSE listener, stub/real camera paths. |
| Cloud service | Stable | FastAPI app with OpenAI/Gemini consensus, filesystem datalake, capture index. |
| Dashboard | Stable | Normal-description editor, trigger controls, capture gallery with filters. |
| Deployment | In progress | Railway deployment proven; need scripted provisioning and monitoring hooks. |
| QA / Testing | In progress | Unit tests for consensus, UI routes, AI clients; add integration smoke and load checks. |
| Security | Not started | No auth yet; relying on secret URLs and network isolation. |

---

## TODO

1. "Send email" feature needs to be added.
   1. shortest interval needs to be set as 10 mins
   2. in the email, we need to give a link to the webui to see the failure. 
2. Make the cloud and device run stably for at least one week without stopping.
   - Add exponential backoff and logging to the SSE reconnect loop (`device.main`).
   - Capture and archive logs for the burn-in run.
3. Implement WiFi setup by AP function.
4. Draft deployment script (Makefile or PowerShell) to spin up local cloud plus stub device.
5. Evaluate lightweight auth strategy (shared API token vs. signed requests) and implement a POC.
6. Document the normal-description workflow in `README` (include Docker/Railway path notes).
7. If the image has no difference, then do not use AI, and use the same state of the prevous one. 
8. Compare the speed of inference at the cloud or at the device. Then choose a better one. 
9. In cloud, show the uploaded the image immedidately after the upload. Before the evaluation, show pending, After evaluation, show the result. 

---

## Recent Wins

- `RecentCaptureIndex` keeps the gallery responsive even with large capture sets.
- Normal-description edits now cascade to nested classifiers, removing stale prompts.
- Consensus labels render as `Agent1` / `Agent2` in the UI while server logs retain real provider names.
- Railway start command uses `/mnt/data` volume for guidance files and the datalake; manual-trigger timeout guidance added.
- Streak-based image pruning (CLI-configurable) now trims duplicate JPEGs while still recording capture metadata.

---

## Watchouts

| Risk | Impact | Mitigation |
| --- | --- | --- |
| Vendor API limits (OpenAI/Gemini) | 429s on classification calls | Rate-limit on device, queue retries with debounce, add single-agent fallback. |
| Filesystem datalake durability | Capture loss on local disk failure | Move to object storage (S3/MinIO) with scheduled backups and DB metadata. |
| Lack of auth | Unauthorized uploads/config changes | Ship API tokens and dashboard login before pilot deployment. |
| SSE idle timeouts (Railway) | Manual-trigger listener churn | Increase server read timeout and add keep-alive heartbeats. |

---

## Reference

- Tests: `python -m unittest discover tests`
- Device smoke test: `python -m device.main --camera stub --camera-source samples/test.jpg --api http --api-url http://127.0.0.1:8000 --iterations 3 --verbose`
- Railway start command:
  ```bash
  python -m cloud.api.main \
    --classifier consensus \
    --normal-description-path /mnt/data/config/normal_guidance.txt \
    --datalake-root /mnt/data/datalake
  ```
