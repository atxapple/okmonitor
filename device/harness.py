from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from .actuator import Actuator
from .capture import Camera, Frame, StubCamera
from .loopback import LoopbackDigitalIO, TriggerEvent
from .trigger import Trigger


class OkApiClient(Protocol):
    def classify(self, frame: Frame, metadata: dict[str, str]) -> dict[str, str]:
        ...


@dataclass
class HarnessConfig:
    iterations: int = 3
    trigger_timeout: float = 1.0
    save_frames_dir: Path | None = None
    verbose: bool = False


class TriggerCaptureActuationHarness:
    """Coordinates trigger -> capture -> API -> actuation."""

    def __init__(
        self,
        io: LoopbackDigitalIO,
        api_client: OkApiClient,
        camera: Camera | None = None,
        trigger: Trigger | None = None,
        actuator: Actuator | None = None,
        config: HarnessConfig | None = None,
    ) -> None:
        self._io = io
        self._api = api_client
        self._camera: Camera = camera or StubCamera()
        self._trigger = trigger or Trigger(io)
        self._actuator = actuator or Actuator(io)
        self._config = config or HarnessConfig()

    def run_once(self, metadata: dict[str, str]) -> TriggerEvent | None:
        event = self._trigger.next_event(timeout=self._config.trigger_timeout)
        if event is None:
            if self._config.verbose:
                print("[harness] No trigger before timeout")
            return None

        frame = self._camera.capture()
        self._debug_frame_capture(event, frame)
        payload = {"trigger_label": event.label, **metadata}
        result = self._api.classify(frame, payload)
        state = result.get("state", "normal")
        self._actuator.set_state(state.lower() == "abnormal")
        return event

    def run(self, metadata: dict[str, str]) -> int:
        processed = 0
        for _ in range(self._config.iterations):
            event = self.run_once(metadata=metadata)
            if event is None:
                break
            processed += 1
        return processed

    def close(self) -> None:
        if hasattr(self._camera, "release"):
            try:
                self._camera.release()
            except Exception:  # pragma: no cover - best effort cleanup
                pass

    def _debug_frame_capture(self, event: TriggerEvent, frame: Frame) -> None:
        if self._config.verbose:
            print(
                f"[harness] Captured frame label={event.label} ts={event.timestamp:.3f} "
                f"size={len(frame.data)} bytes"
            )
        debug_dir = self._config.save_frames_dir
        if not debug_dir:
            return
        debug_dir.mkdir(parents=True, exist_ok=True)
        stem = f"{int(event.timestamp)}_{event.label}"
        frame_path = debug_dir / f"{stem}.{frame.encoding}"
        frame_path.write_bytes(frame.data)
        if self._config.verbose:
            print(f"[harness] Saved frame to {frame_path}")


__all__ = ["TriggerCaptureActuationHarness", "HarnessConfig"]