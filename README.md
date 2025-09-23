# okmonitor

## Environment configuration

1. Copy `.env.example` to `.env` and populate the required secrets (e.g., `OPENAI_API_KEY`, `GEMINI_API_KEY`).
2. Optional: add other overrides (such as `DEVICE_ID`) you want the server to pick up automatically.
3. Start the API server; it will load variables from `.env` before reading your shell environment.

## OpenAI-powered classification

1. Ensure your OpenAI API key is set (via `.env` or `set OPENAI_API_KEY=sk-...`).
2. Create a text file that describes what a "normal" capture should look like.
3. Run the API server with:
   ``python -m cloud.api.main --classifier openai --normal-description-path path\to\normal.txt``

Captured images will be classified as `normal`, `abnormal`, or `unexpected` using the supplied guidance. When the result is `abnormal`, the API includes a short `reason` explaining the anomaly; the capture metadata stored in `cloud_datalake/` records the same justification.

## Web dashboard

Visit `http://127.0.0.1:8000/ui` while the API server is running to:
- Update the "normal" environment description (persisted back to the configured text file and applied to the classifier at runtime).
- Configure how often the device should capture images by toggling the recurring trigger interval.
- Review the latest captured images, including state, confidence, trigger label, and any abnormal reasoning returned by the classifier.

The dashboard now only stores configuration; it no longer touches the physical camera. Devices poll `/v1/device-config` to pick up the current interval and description, capture frames locally, and upload them to `/v1/captures`.

## Device harness quickstart

```
python -m device.main \
  --camera opencv --camera-source 0 \
  --api http --api-url http://127.0.0.1:8000 \
  --device-id floor-01-cam --iterations 0 --verbose
```

Set `--iterations 0` to let the device follow the cloud-provided schedule indefinitely. For testing without a camera, use `--camera stub --camera-source samples/test.jpg`.
