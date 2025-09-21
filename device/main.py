from __future__ import annotations

import argparse
import time
from pathlib import Path
import platform
from typing import Any, Dict, Sequence

import requests

from device.actuator import Actuator
from device.capture import OpenCVCamera, StubCamera
from device.harness import HarnessConfig, TriggerCaptureActuationHarness
from device.loopback import LoopbackDigitalIO
from device.trigger import Trigger
from cloud.api.client import OkApiHttpClient
from cloud.api.mock import MockOkApi


def parse_resolution(value: str | None) -> tuple[int, int] | None:
    if value is None:
        return None
    parts = value.lower().split("x")
    if len(parts) != 2:
        raise argparse.ArgumentTypeError("resolution must be WIDTHxHEIGHT")
    width, height = parts
    try:
        return int(width), int(height)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("resolution must be numeric") from exc


def parse_backend(value: str | None) -> str | int | None:
    if value is None:
        return None
    value = value.strip()
    if not value:
        return None
    try:
        return int(value)
    except ValueError:
        return value


def build_camera(
    kind: str,
    source: str,
    resolution: tuple[int, int] | None,
    backend: str | int | None,
    warmup_frames: int,
) -> OpenCVCamera | StubCamera:
    if kind == "opencv":
        try:
            converted_source: int | str = int(source)
        except ValueError:
            converted_source = source

        backend_to_use = backend
        preferred_attempted = False
        if backend_to_use is None and platform.system().lower().startswith("win"):
            backend_to_use = "dshow"
            preferred_attempted = True

        try:
            return OpenCVCamera(
                source=converted_source,
                resolution=resolution,
                backend=backend_to_use,
                warmup_frames=warmup_frames,
            )
        except RuntimeError:
            if preferred_attempted:
                return OpenCVCamera(
                    source=converted_source,
                    resolution=resolution,
                    backend=None,
                    warmup_frames=warmup_frames,
                )
            raise
    sample = Path(source) if source else None
    return StubCamera(sample_path=sample if sample and sample.exists() else None)


def build_api_client(args: argparse.Namespace) -> MockOkApi | OkApiHttpClient:
    if args.api == "http":
        return OkApiHttpClient(base_url=args.api_url, timeout=args.api_timeout)
    return MockOkApi(default_state=args.force_state or "normal")


def fetch_device_config(api_url: str, device_id: str, timeout: float) -> Dict[str, Any] | None:
    url = f"{api_url.rstrip('/')}/v1/device-config"
    try:
        response = requests.get(url, params={"device_id_override": device_id}, timeout=timeout)
        response.raise_for_status()
    except requests.RequestException as exc:
        print(f"[device] Failed to fetch device config: {exc}")
        return None
    try:
        return response.json()
    except ValueError:
        print("[device] Invalid JSON in device config response")
        return None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the OK Monitor trigger/capture harness")
    parser.add_argument("--camera", choices=["stub", "opencv"], default="stub", help="camera backend to use")
    parser.add_argument(
        "--camera-source",
        default="0",
        help="camera source index or path (OpenCV) or sample image path (stub)",
    )
    parser.add_argument(
        "--camera-resolution",
        default=None,
        help="force camera resolution WIDTHxHEIGHT (only for OpenCV backend)",
    )
    parser.add_argument(
        "--camera-backend",
        default=None,
        help="preferred OpenCV backend (e.g. dshow, msmf, 700)",
    )
    parser.add_argument(
        "--camera-warmup",
        type=int,
        default=2,
        help="number of frames to discard after opening the camera",
    )
    parser.add_argument(
        "--api",
        choices=["mock", "http"],
        default="mock",
        help="API backend to use",
    )
    parser.add_argument(
        "--api-url",
        default="http://127.0.0.1:8000",
        help="Base URL for HTTP API client",
    )
    parser.add_argument("--api-timeout", type=float, default=20.0, help="HTTP API timeout in seconds")
    parser.add_argument("--iterations", type=int, default=5, help="maximum trigger events to process (0 for schedule mode)")
    parser.add_argument("--trigger-timeout", type=float, default=0.2, help="seconds to wait for trigger")
    parser.add_argument(
        "--save-frames-dir",
        default="debug_captures",
        help="directory to store captured frames (set empty string to disable)",
    )
    parser.add_argument("--verbose", action="store_true", help="enable verbose harness logging")
    parser.add_argument(
        "--force-state",
        choices=["normal", "abnormal"],
        default=None,
        help="optional override for mock API classification",
    )
    parser.add_argument("--device-id", default="demo-device", help="Device identifier to send to the API")
    parser.add_argument(
        "--config-poll-interval",
        type=float,
        default=5.0,
        help="Seconds between configuration refreshes when running in schedule mode",
    )
    return parser


def run_schedule(
    harness: TriggerCaptureActuationHarness,
    io: LoopbackDigitalIO,
    api_client: MockOkApi | OkApiHttpClient,
    args: argparse.Namespace,
) -> None:
    metadata = {"device_id": args.device_id}
    poll_interval = max(1.0, float(args.config_poll_interval))

    print("[device] Entering scheduled capture mode. Press Ctrl+C to stop.")

    config_cache: Dict[str, Any] = {}
    last_config_refresh = 0.0
    next_capture_at: float | None = None
    last_manual_counter: int | None = None
    pending_manual_captures = 0

    try:
        while True:
            now = time.monotonic()

            if isinstance(api_client, MockOkApi):
                config_cache = {
                    "trigger": {"enabled": True, "interval_seconds": poll_interval},
                    "normal_description": "",
                    "manual_trigger_counter": last_manual_counter or 0,
                }
                last_config_refresh = now
            elif now - last_config_refresh >= poll_interval or not config_cache:
                fresh = fetch_device_config(args.api_url, args.device_id, args.api_timeout)
                if fresh is not None:
                    if fresh != config_cache and args.verbose:
                        print(f"[device] Received new config: {fresh}")
                    config_cache = fresh
                    next_capture_at = None
                last_config_refresh = now

            trigger_cfg = (config_cache or {}).get("trigger", {})
            enabled = bool(trigger_cfg.get("enabled"))
            interval = trigger_cfg.get("interval_seconds")

            manual_counter = (config_cache or {}).get("manual_trigger_counter")
            if manual_counter is not None:
                manual_counter = int(manual_counter)
                if last_manual_counter is None:
                    last_manual_counter = manual_counter
                elif manual_counter > last_manual_counter:
                    pending_manual_captures += manual_counter - last_manual_counter
                    last_manual_counter = manual_counter

            if pending_manual_captures > 0:
                next_capture_at = now

            if not enabled or not interval or interval <= 0:
                if args.verbose:
                    print(f"[device] Trigger disabled; sleeping for {poll_interval}s")
                next_capture_at = None
                time.sleep(poll_interval)
                continue

            if next_capture_at is None:
                next_capture_at = now

            sleep_for = next_capture_at - now
            if sleep_for > 0:
                time.sleep(min(sleep_for, poll_interval))
                continue

            start = time.monotonic()
            if pending_manual_captures > 0:
                label = f"manual-{int(time.time())}-{pending_manual_captures}"
                pending_manual_captures -= 1
            else:
                label = f"schedule-{int(time.time())}"
            io.inject_trigger(label=label)
            try:
                event = harness.run_once(metadata=metadata)
            except Exception as exc:  # pragma: no cover - runtime condition
                print(f"[device] Capture/upload failed: {exc}")
                next_capture_at = time.monotonic() + (float(interval) if interval else poll_interval)
                time.sleep(poll_interval)
                continue

            if event is not None and args.verbose:
                print(f"[device] Captured trigger {event.label} at interval {interval:.2f}s")

            if pending_manual_captures > 0:
                next_capture_at = time.monotonic()
            else:
                next_capture_at = (next_capture_at or start) + float(interval)
                now_after = time.monotonic()
                if next_capture_at <= now_after:
                    drift = now_after - next_capture_at
                    skip = int(drift // interval) + 1
                    next_capture_at += skip * float(interval)
    except KeyboardInterrupt:
        print("[device] Schedule stopped by user")


def run_demo(argv: Sequence[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)

    resolution = parse_resolution(args.camera_resolution)
    backend = parse_backend(args.camera_backend)
    camera = build_camera(args.camera, args.camera_source, resolution, backend, args.camera_warmup)

    io = LoopbackDigitalIO()
    api_client = build_api_client(args)
    trigger = Trigger(io)
    actuator = Actuator(io)
    save_dir = Path(args.save_frames_dir) if args.save_frames_dir else None
    harness = TriggerCaptureActuationHarness(
        io=io,
        api_client=api_client,
        camera=camera,
        trigger=trigger,
        actuator=actuator,
        config=HarnessConfig(
            iterations=max(1, args.iterations) if args.iterations > 0 else 1,
            trigger_timeout=args.trigger_timeout,
            save_frames_dir=save_dir,
            verbose=args.verbose,
        ),
    )

    try:
        if args.iterations > 0:
            for idx in range(args.iterations):
                io.inject_trigger(label=f"demo-{idx}")
            metadata = {"device_id": args.device_id}
            processed = harness.run(metadata=metadata)
            print(f"Processed {processed} trigger(s)")
            print("Actuation log:")
            for ts, state in io.actuation_log:
                print(f"  ts={ts:.3f} state={state}")
        else:
            run_schedule(harness, io, api_client, args)
    finally:
        harness.close()


if __name__ == "__main__":
    run_demo()


