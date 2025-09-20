from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

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
        return OpenCVCamera(
            source=converted_source,
            resolution=resolution,
            backend=backend,
            warmup_frames=warmup_frames,
        )
    sample = Path(source) if source else None
    return StubCamera(sample_path=sample if sample and sample.exists() else None)


def build_api_client(args: argparse.Namespace) -> MockOkApi | OkApiHttpClient:
    if args.api == "http":
        return OkApiHttpClient(base_url=args.api_url, timeout=args.api_timeout)
    return MockOkApi(default_state=args.force_state or "normal")


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
    parser.add_argument("--api-timeout", type=float, default=5.0, help="HTTP API timeout in seconds")
    parser.add_argument("--iterations", type=int, default=5, help="maximum trigger events to process")
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
    return parser


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
            iterations=args.iterations,
            trigger_timeout=args.trigger_timeout,
            save_frames_dir=save_dir,
            verbose=args.verbose,
        ),
    )

    try:
        for idx in range(args.iterations):
            io.inject_trigger(label=f"demo-{idx}")
        metadata = {"device_id": args.device_id}
        processed = harness.run(metadata=metadata)
        print(f"Processed {processed} trigger(s)")
        print("Actuation log:")
        for ts, state in io.actuation_log:
            print(f"  ts={ts:.3f} state={state}")
    finally:
        harness.close()


if __name__ == "__main__":
    run_demo()