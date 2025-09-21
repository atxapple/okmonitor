# OK Monitor Project Management

## Current Status

- **Device-driven capture loop**: Device owns the camera, polls `/v1/device-config`, and captures on schedule with drift compensation.
- **Cloud inference service**: Receives captures at `/v1/captures`, runs `gpt-4o-mini` (configurable) to classify as normal/abnormal/unexpected, stores records in the filesystem datalake.
- **Configuration UI**: Web dashboard updates normal description, controls recurring trigger interval, and shows recent captures with download links; auto refresh is optional and pauses while editing.
- **Tests & automation**: Unit tests cover OpenAI client, UI routes, and config endpoints; basic workflow validated via `python -m unittest discover tests`.

## Remaining Work

### MVP Completion

1. **Image Capture Trigger**

2. **Abnormal Detection Output**

3. **Error resilience**
   - Retry/backoff on capture upload timeouts instead of single retries.
   - Better messaging in the UI when the OpenAI classification fails.
4. **Configuration security**
   - Add API auth (token or key) for `/v1/captures` and `/v1/device-config` to prevent unauthorized access.
5. **Operational usage**
   - Provide quickstart scripts or makefiles for running server + device together.
   - Add logging configuration and log rotation for both processes.
6. **Documentation**
   - Expand README with architecture diagram, API references, and troubleshooting guide.

### Toward Productization

1. **Scalability & deployment**
   - Deploy cloud service to managed infrastructure (e.g., containerized on ECS/GKE) with persistent storage (S3, database for metadata).
   - Use async task queue (Celery/Cloud Tasks) for classification to avoid blocking uploads, add rate limiting.
2. **Device management**
   - Device provisioning, heartbeat, and centralized monitoring.
   - Over-the-air configuration updates and firmware/software version tracking.
3. **Advanced UI**
   - Real-time capture stream (websocket or server-sent events) with filtering/search.
   - Role-based access control, user accounts, and audit trail.
4. **Observability**
   - Metrics dashboards (classification counts, latency, health checks).
   - Alerts for abnormal spikes or device inactivity.
5. **Compliance & privacy**
   - Define retention policies, secure storage (encryption at rest), and opt-in consent handling for captures.

## Next Steps

- Finalize MVP error handling and auth.
- Add deployment scripts for staging environment.
- Prioritize productization roadmap milestones based on stakeholder feedback.
## Potential Applications & Target Users

- **Manufacturing quality control**
  - *Who*: Production engineers and line supervisors.
  - *Use*: Mount cameras on workcells to verify that assemblies match “normal” visual criteria (correct parts fitted, safety guards closed). Alerts prompt operators to stop the line.

- **Facility safety compliance**
  - *Who*: EHS (Environment, Health & Safety) teams.
  - *Use*: Watch critical zones—e.g., ensure PPE is worn, fire exits remain clear, machinery enclosures are shut—and document incidents with automated abnormal snapshots.

- **Pharmaceutical & food labs**
  - *Who*: Lab managers, QA teams.
  - *Use*: Monitor sterile environments for unexpected objects or open containers, keeping logs for audit trails.

- **Data center / server room ops**
  - *Who*: Site reliability and infrastructure managers.
  - *Use*: Detect when cabinet doors are ajar, cables are unplugged, or unauthorized equipment appears, triggering maintenance tickets.

- **Retail loss prevention**
  - *Who*: Store managers, security teams.
  - *Use*: Classify back-room stock areas or checkout lanes, flagging abnormal scenes (e.g., unauthorized access, empty shelves).

- **Healthcare & elder care monitoring**
  - *Who*: Caregivers, hospital facility staff.
  - *Use*: Observe patient rooms for abnormal states (patient not in bed, equipment disconnected) without storing continuous video.

- **Construction site oversight**
  - *Who*: Project managers, safety inspectors.
  - *Use*: Capture periodic snapshots to ensure scaffolding, barriers, or materials remain in expected configurations.

Each of these groups benefits from the system’s ability to learn “normal” conditions, automatically capture deviations, and provide a reviewable image log with classification confidence.
