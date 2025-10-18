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
   Add `--streak-pruning-enabled --streak-threshold 10 --streak-keep-every 5` to keep metadata for every capture while only persisting a JPEG when a device reports the same state throughout the configured streak window.

Captured images will be classified as `normal`, `abnormal`, or `uncertain` using the supplied guidance. An `uncertain` result indicates low model confidence or disagreement between ensemble models. When the result is `abnormal`, the API includes a short `reason` explaining the anomaly; the capture metadata stored in `cloud_datalake/` records the same justification.

## Web dashboard

Visit `http://127.0.0.1:8000/ui` while the API server is running to:
- Update the "normal" environment description (persisted back to the configured text file and applied to the classifier at runtime).
- Configure how often the device should capture images by toggling the recurring trigger interval.
- Review the latest captured images, including state, confidence, trigger label, and any abnormal reasoning returned by the classifier.
- Hover over a capture timestamp to see the device-supplied capture time alongside the cloud ingest time.

The dashboard now only stores configuration; it no longer touches the physical camera. Devices poll `/v1/device-config` to pick up the current interval and description, capture frames locally, and upload them to `/v1/captures`.

## Device harness quickstart

```
python -m device.main \
  --camera opencv --camera-source 0 \
  --api http --api-url http://127.0.0.1:8000 \
  --device-id floor-01-cam --iterations 0 --verbose
```

Set `--iterations 0` to let the device follow the cloud-provided schedule indefinitely. For testing without a camera, use `--camera stub --camera-source samples/test.jpg`.
Custom device clients should include an ISO8601 `captured_at` value in `/v1/captures` requests; the bundled harness does this automatically so the datalake, filenames, and UI reflect the device clock rather than the server arrival time.

## Email alerts

To deliver an email whenever a capture is classified as abnormal:

1. Set `SENDGRID_API_KEY` with a valid SendGrid API key.
2. Set `ALERT_FROM_EMAIL` to the verified sender address.
3. Optional: set `ALERT_ENVIRONMENT_LABEL` to tag alert subjects (for example, `staging`).
4. Use the dashboard's **Notification & Actions** card to add recipient email addresses and enable alerts.

The server persists notification preferences in `config/notifications.json`. If any required value is missing at startup, the API logs the gap and continues without sending alerts.

## Deploying to Railway

Railway mounts your project volume at `/mnt/data`, so point both the normal-description file and the datalake there. The recommended custom start command is:

```bash
python -m cloud.api.main \
  --classifier consensus \
  --normal-description-path /mnt/data/config/normal_guidance.txt \
  --datalake-root /mnt/data/datalake \
  --streak-pruning-enabled \
  --streak-threshold 5 \
  --streak-keep-every 10
```

This keeps capture metadata for every upload while trimming redundant JPEGs after five identical states, retaining one image every ten captures during a streak.

### Execution options for streak pruning

Use the streak pruning flags together to control how aggressively the server persists identical captures:

- `--streak-pruning-enabled`: toggles pruning on. When omitted, every capture image is stored regardless of duplication.
- `--streak-threshold <int>`: number of consecutive identical states before pruning activates. For example, `--streak-threshold 5` starts discarding redundant JPEGs after the fifth identical result.
- `--streak-keep-every <int>`: frequency (in captures) at which a JPEG is still saved while pruning is active. Setting `--streak-keep-every 10` preserves one representative image out of every ten duplicates, while still retaining metadata for all captures.

Example with conservative pruning:

```bash
python -m cloud.api.main \
  --streak-pruning-enabled \
  --streak-threshold 8 \
  --streak-keep-every 4
```

This keeps metadata for every capture, waits for eight identical classifications before trimming images, and still writes one JPEG every four captures during a streak so you maintain visual checkpoints.

## Similarity-based reuse

When frames remain visually unchanged, enable the similarity cache to skip vendor inference after the streak threshold is reached:

```bash
python -m cloud.api.main \
  --similarity-enabled \
  --similarity-threshold 6 \
  --similarity-expiry-minutes 60 \
  --similarity-cache-path config/similarity_cache.json
```

With the cache active the server computes a perceptual hash for each capture; once a device reports the same classification at least `--streak-threshold` times and the hash stays within the configured Hamming distance, the previous result is returned instantly. Metadata continues to be recorded while AI calls are skipped.

Behind the scenes the server converts each image to an 8×8 grayscale thumbnail and builds a 64‑bit average hash. The hash, classification result, record id, score, and reasoning text are stored per device in `--similarity-cache-path` (JSON on disk). On each new capture the service checks that streak pruning has already crossed `--streak-threshold`, then compares the new hash to the cached value; if the Hamming distance is within `--similarity-threshold`, the cached result is reused and the image bypasses model inference. Entries expire after `--similarity-expiry-minutes` so stale states are cleared automatically.

## Choosing classifier backends

The primary and secondary agents are selectable via CLI. By default `--classifier consensus` uses OpenAI (`primary`) and Gemini (`secondary`). Override either slot with:

```bash
python -m cloud.api.main \
  --primary-backend openai \
  --secondary-backend gemini \
  --openai-model gpt-4o-mini \
  --gemini-model models/gemini-2.5-flash
```

Set the corresponding API keys in your environment (`OPENAI_API_KEY`, `GEMINI_API_KEY`). Use `--secondary-backend none` if you want a single-agent configuration with no consensus. Both backends accept `--*-model`, `--*-base-url`, and `--*-api-key-env` flags so you can mix and match providers without code changes.

## API server CLI reference

- **Server binding & storage**: `--host` (default `0.0.0.0`) picks the interface, `--port` (default `8000`) selects the listening port, `--datalake-root` chooses where captures are written, and `--normal-description-path` points to the baseline guidance file surfaced in the UI. Set `--notification-config-path` if the notification JSON lives somewhere else.
- **Classifier layout**: `--classifier` selects the built-in preset (`simple`, `openai`, `gemini`, or `consensus`). Override the participants with `--primary-backend` and `--secondary-backend` (`none` disables the secondary) and expose a specific device name to UI clients with `--device-id`.
- **Provider configuration**: For OpenAI use `--openai-model`, `--openai-base-url`, `--openai-timeout`, and `--openai-api-key-env` (default `OPENAI_API_KEY`). Gemini equivalents are `--gemini-model`, `--gemini-base-url`, `--gemini-timeout`, and `--gemini-api-key-env` (default `GEMINI_API_KEY`).
- **Capture dedupe & reuse**: Enable metadata-only repeats with `--dedupe-enabled`, tune the trigger point via `--dedupe-threshold` (default `3` identical states), and keep snapshots every `--dedupe-keep-every` captures (default `5`). Layer similarity caching with `--similarity-enabled`, `--similarity-threshold` (default Hamming distance `6`), `--similarity-expiry-minutes` (default `60`, `0` never expires), and `--similarity-cache-path` for persistence.
- **Streak pruning controls**: Combine `--streak-pruning-enabled` with `--streak-threshold` (default `10`) and `--streak-keep-every` (default `5`) to govern how many redundant JPEGs survive a long-running identical streak.
- **Email alerts**: Supply SendGrid credentials through the env vars named by `--sendgrid-api-key-env` (default `SENDGRID_API_KEY`) and `--alert-from-email-env` (default `ALERT_FROM_EMAIL`). Add an optional prefix with `--alert-environment-label-env`. Missing credentials automatically disable outbound email while preserving metadata logging.

## Device harness CLI reference

- **Capture backend**: `--camera` chooses `opencv` or `stub`, `--camera-source` passes the index/path (default `0`), `--camera-resolution` enforces `WIDTHxHEIGHT`, `--camera-backend` picks a specific OpenCV backend (e.g. `dshow`, `msmf`, numeric ID), and `--camera-warmup` discards the first N frames (default `2`) after opening the feed.
- **API connectivity**: `--api` toggles between the local `mock` responder and real `http`, while `--api-url` (default `http://127.0.0.1:8000`) and `--api-timeout` (default `20` seconds) configure the HTTP client.
- **Scheduling & triggers**: `--iterations` caps the number of cycles (`0` lets the cloud schedule drive the loop), `--trigger-timeout` (default `0.2` seconds) defines how long to block for trigger input, and `--config-poll-interval` (default `5.0` seconds, minimum enforced at `1`) determines how often schedule mode refreshes device config.
- **Diagnostics & capture artifacts**: `--save-frames-dir` names the folder for raw capture dumps (empty string disables) and `--verbose` prints harness chatter including manual trigger streaming updates.
- **Mock behavior**: Use `--force-state` with `normal` or `abnormal` to pin the mock API's classification, and keep `--device-id` aligned with the ID that the server exposes over `/v1/device-config`.
