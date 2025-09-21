# OK Monitor Project Management

## Current Status

- **Device-driven capture loop**: Device owns the camera, polls `/v1/device-config`, and captures on schedule with drift compensation.
- **Cloud inference service**: Receives captures at `/v1/captures`, runs `gpt-4o-mini` (configurable) to classify as normal/abnormal/unexpected, stores records in the filesystem datalake.
- **Configuration UI**: Web dashboard updates normal description, controls recurring trigger interval, and shows recent captures with download links; auto refresh is optional and pauses while editing.
- **Tests & automation**: Unit tests cover OpenAI client, UI routes, and config endpoints; basic workflow validated via `python -m unittest discover tests`.

## Remaining Work

### MVP Completion

1. **Error resilience**
   - Retry/backoff on capture upload timeouts instead of single retries.
   - Better messaging in the UI when the OpenAI classification fails.
2. **Configuration security**
   - Add API auth (token or key) for `/v1/captures` and `/v1/device-config` to prevent unauthorized access.
3. **Operational usage**
   - Provide quickstart scripts or makefiles for running server + device together.
   - Add logging configuration and log rotation for both processes.
4. **Documentation**
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
