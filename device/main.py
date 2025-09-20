from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from device.actuator import Actuator
from device.capture import OpenCVCamera, StubCamera
from device.harness import HarnessConfig, TriggerCaptureActuationHarness
from device.loopback import LoopbackDigitalIO
from device.trigger import Trigger
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


def build_camera(kind: str, source: str, resolution: tuple[int, int] | None) -> OpenCVCamera | StubCamera:
    if kind == "opencv":
        try:
            converted_source: int | str = int(source)
        except ValueError:
            converted_source = source
        return OpenCVCamera(source=converted_source, resolution=resolution)
    sample = Path(source) if source else None
    return StubCamera(sample_path=sample if sample and sample.exists() else None)


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
    return parser


def run_demo(argv: Sequence[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)

    resolution = parse_resolution(args.camera_resolution)
    camera = build_camera(args.camera, args.camera_source, resolution)

    io = LoopbackDigitalIO()
    api = MockOkApi(default_state=args.force_state or "normal")
    trigger = Trigger(io)
    actuator = Actuator(io)
    save_dir = Path(args.save_frames_dir) if args.save_frames_dir else None
    harness = TriggerCaptureActuationHarness(
        io=io,
        api_client=api,
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
        processed = harness.run(metadata={"device_id": "demo-device"})
        print(f"Processed {processed} trigger(s)")
        print("Actuation log:")
        for ts, state in io.actuation_log:
            print(f"  ts={ts:.3f} state={state}")
    finally:
        harness.close()


if __name__ == "__main__":
    run_demo()