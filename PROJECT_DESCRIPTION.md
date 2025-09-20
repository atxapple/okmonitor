# OK Monitor — Step‑by‑Step Development Plan (v2.0)

> Vision: A cloud‑connected camera system that captures an image when triggered, uploads it to the cloud AI service for classification (**Normal / Warning / Abnormal**), and drives digital outputs accordingly. Continuous improvement happens through human labels provided via a web UI.

---

## 0) Product Goals & Non‑Goals

**Goals**

* Cloud‑based AI inference (no heavy AI model on device).
* Three‑state outcome: Normal / Warning / Abnormal (warning is optional/renameable).
* Human‑in‑the‑loop labeling and rule definitions via web UI.
* Pluggable hardware I/O: digital inputs (DI) to trigger capture; digital outputs (DO) to actuate.
* Modular services to scale to multi‑camera, multi‑site deployments.
* Device requires internet connectivity (design assumes always‑online).

**Non‑Goals (v1)**

* No offline inference; device won’t classify without internet.
* No safety‑certified use.

---

## 1) System Architecture (Device + Cloud)

**Device (edge hardware near camera):**

* `ok-trigger` — reads DI; emits Trigger events.
* `ok-capture` — controls camera; captures image on trigger.
* `ok-agent` — uploads images & metadata to cloud; receives classification result & config.
* `ok-actuator` — toggles DO pins based on cloud decision.
* Local storage — minimal (temporary buffer until upload acknowledged).

**Cloud:**

* `ok-api` — central backend (REST/gRPC) for devices, users, configs.
* `ok-ai` — inference service using scalable GPU/CPU nodes.
* `ok-datalake` — object store (S3/MinIO) for images and model artifacts.
* `ok-trainer` — training jobs, active learning, model registry.
* `ok-admin` — management UI for orgs, devices, models.

**Web UI:**

* `ok-ui` — labeling, review, rule editing, dashboards.

**Protocol:** HTTPS REST (JSON). Device pushes → Cloud responds with result.

---

## 2) End‑to‑End Data Flow (nominal)

1. **Trigger** from DI or API.
2. **Capture** image.
3. **Upload** image + metadata to `ok-api`.
4. **Inference** `ok-ai` classifies → Normal/Warning/Abnormal.
5. **Decision** result returned to device.
6. **Actuate** `ok-actuator` toggles DO pins.
7. **Persist** image, prediction, label candidates in cloud.
8. **Review** Operator labels via UI.
9. **Train** `ok-trainer` updates model; deploys new version.

---

## 3) Device Modules

### `ok-trigger`

* Monitors DI lines; debounces; emits trigger events.

### `ok-capture`

* Supports USB/RTSP cameras.
* API: capture frame → returns image.

### `ok-agent`

* Handles HTTPS connection to cloud.
* Retries on upload failures.
* Sends metadata (device\_id, camera\_id, ts).
* Waits for classification result; forwards to actuator.

### `ok-actuator`

* Receives classification result from agent.
* Maps Normal/Warning/Abnormal to DO pins.
* Configurable pulse/steady signals.

---

## 4) Cloud Services

### `ok-api`

* Device authentication.
* Image + metadata ingestion.
* Routes to inference service.
* Returns classification to device.

### `ok-ai`

* Scalable inference (Docker + K8s).
* ONNX/PyTorch/TensorFlow models.

### `ok-datalake`

* Stores images, metadata, decisions.

### `ok-trainer`

* Active learning.
* Retrains with human labels.
* Model registry & deployment.

### `ok-admin` & `ok-ui`

* Live panels, labeling interface, rule editor, dashboards.

---

## 5) ML Strategy (Cloud‑based)

**Phase A (MVP):** anomaly detection with embeddings.
**Phase B:** supervised fine‑tune with human labels.
**Phase C:** task‑specific models.

Active learning selects uncertain images for labeling.

---

## 6) Rules & Configuration

* Rules stored in cloud DB.
* Synced to devices (e.g., DO mapping, thresholds, timing).
* Editable via web UI.

---

## 7) Web UI — Key Screens

* **Live Panel:** incoming images, predicted outcome, label buttons.
* **Label Studio:** confirm/reject predictions.
* **Rules Editor:** DO mappings, thresholds.
* **Model Page:** versions, metrics.
* **Fleet View:** device list, online status, last sync.

---

## 8) Hardware I/O Considerations

* **DI:** opto‑isolated 24V.
* **DO:** relay/SSR, configurable mapping.
* Device assumes internet connection; buffering if temporarily offline.

---

## 9) Development Phases

**Phase 0 — Spec**

* Confirm requirements, IO design.

**Phase 1 — Device MVP**

* Trigger → Capture → Upload → Classification → Actuation.

**Phase 2 — Web UI & Labeling**

* Live image view; label buttons.

**Phase 3 — Training Pipeline**

* Active learning; retrain loop.

**Phase 4 — Multi‑device Fleet Management**

* Device registry; OTA updates.

---

## 10) Repository Structure

```
ok-monitor/
  device/
    agent/
    trigger/
    capture/
    actuator/
  cloud/
    api/
    ai/
    trainer/
    datalake/
  ui/
    web/
  docs/
```

---

## 11) Testing Strategy

* **Device Integration Test:** trigger loopback → upload → classification → DO.
* **Cloud Test:** load testing inference pipeline.
* **E2E Test:** simulate 1000 triggers/hour.

---

## 12) Security

* TLS for all communication.
* Device keys for auth.
* Signed model/config updates.

---

## 13) Acceptance Criteria

* Trigger → DO response < 500 ms (network permitting).
* Label UI usable on desktop/tablet.
* Retrain pipeline can produce new model in < 24h.

---

### Notes

* Architecture is simpler (device only does trigger/capture/upload/actuation).
* Cloud handles AI inference & heavy lifting.
* Requires stable connectivity; fallback = buffer & retry.
