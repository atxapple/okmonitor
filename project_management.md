# OK Monitor Project Management

## Current Status

- **Device-driven capture loop**: Device owns the camera, opens a low-latency SSE channel to the cloud, reacts instantly to manual triggers, and still handles scheduled captures with drift compensation.
- **Cloud inference service**: Receives captures at `/v1/captures`, runs `gpt-4o-mini` (configurable) to classify frames, stores results in the filesystem datalake, and exposes streaming/manual-trigger APIs.
- **Configuration UI**: Dashboard edits the normal description, sets the recurring trigger interval, provides a “Trigger Now” button, download links, and optional auto refresh that pauses during edits.
- **Testing & automation**: Unit tests cover OpenAI client, UI routes, manual trigger workflow, and config endpoints; `python -m unittest discover tests` validates the stack.

## Remaining Work

### MVP Completion

1. **Hardware & webhook trigger inputs**
   - webhook ingestion, recurring trigger, and UI button into unified trigger dispatch.
   - Debounce/rate-limit manual requests and surface acknowledgements in UI/device logs.
   - Integrate digital Input (e.g., GPIO/PLC) is not the scope of MVP. This feature will be added. later. 
2. **Hardware & web notification output**
   - Integrate digital Output (e.g., GPIO/PLC) is not the scope of MVP. This feature will be added. later. 
   - Send notification email 
3. **Robustness & error handling**
   - Add retry/backoff for capture uploads and manual-trigger SSE reconnects with exponential delay.
   - Improve UI/CLI messaging when OpenAI classification fails or network drops.
4. **Security & access control**
   - Introduce API authentication (token/headers) for device/cloud endpoints.
   - Audit logging for manual triggers and configuration changes.
5. **Operational tooling**
   - Provide scripts/docker-compose for running cloud + device, plus logging/rotation configs.
   - Health dashboards (basic metrics, alerts for offline devices).
6. **Documentation**
   - Expand README with architecture diagram, trigger flow, SSE details, and troubleshooting.

### Toward Productization

1. **Scalable deployment**
   - Containerize cloud service, back datalake with S3/object storage + DB metadata, and move classification to async workers.
2. **Fleet management**
   - Device onboarding, heartbeats, firmware/software rollouts, and centralized monitoring UI.
3. **Advanced UI capabilities**
   - Live timelines/filters, user roles, audit trail, and configurable notification routing (email/SMS/Slack).
4. **Observability & analytics**
   - Metrics on trigger sources, response latency, false positives; integrate with monitoring stacks.
5. **Governance & privacy**
   - Retention policies, encryption at rest, user consent flow, and compliance reporting.

## Next Steps

- Implement authenticated webhook + digital IO trigger adapters feeding the existing hub.
- Add retry/backoff and reconnection logic for capture uploads and SSE listeners.
- Extend documentation with deployment guides and API usage examples prior to pilot rollout.

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
