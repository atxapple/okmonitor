# OK Monitor - MVP Scope (v0.1)

> Vision: Deliver a **minimal viable product** that demonstrates end-to-end flow: trigger -> capture -> upload -> cloud classification -> actuation, plus basic labeling via a web UI.

---

## MVP Goals

* Support **one camera** and **one DI/DO pair**.
* Always-online; no offline fallback beyond simple buffer & retry.
* Cloud-based AI model (simple anomaly score).
* Minimal web UI: show latest image + allow operator to label Normal/Abnormal.
* Secure device <-> cloud communication.

**Not in MVP**

* Multi-device or fleet management.
* Complex rule engine or Warning state.
* Advanced UI (dashboards, rule editor, model metrics).
* Automated retraining pipeline (manual retrain only).

---

## MVP Architecture

**Device:**

* `ok-trigger` - DI input to detect trigger.
* `ok-capture` - capture single frame.
* `ok-agent` - upload image + metadata; receive classification result.
* `ok-actuator` - set DO pin based on result (Normal vs Abnormal).

**Cloud:**

* `ok-api` - receive upload, route to inference, return result.
* `ok-ai` - simple anomaly model endpoint (embedding + threshold).
* `ok-datalake` - store uploaded images + results.
* `ok-ui` - very basic web page: view last images, label as Normal/Abnormal.

---

## End-to-End Flow

1. DI trigger -> `ok-capture` grabs image.
2. `ok-agent` uploads image to cloud.
3. `ok-ai` classifies -> Normal or Abnormal.
4. `ok-api` returns result.
5. `ok-actuator` sets DO pin accordingly.
6. Operator labels images in `ok-ui`.

---

## Development Phases (MVP)

* **Phase 0:** Hardware setup (camera + DI/DO pins) and cloud API skeleton.
* **Phase 1:** Device flow Trigger -> Capture -> Upload -> Actuate.
* **Phase 2:** Cloud inference stub (e.g., fixed threshold) -> expand to simple embedding model.
* **Phase 3:** Minimal `ok-ui` for image review + labeling.
* **Phase 4:** Integrate labels storage in `ok-datalake`.

---

## Acceptance Criteria (MVP)

* End-to-end trigger -> DO response < 1s.
* System supports at least 10 triggers/min.
* Operator can view & label last 100 images in UI.
* Secure TLS communication with device keys.

---

### Notes

This MVP demonstrates the full pipeline with minimal complexity. Later phases can add Warning state, rule editor, active learning, fleet view, and retraining pipeline.
