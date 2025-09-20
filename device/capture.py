from __future__ import annotations

from dataclasses import dataclass
import base64
import pathlib
from typing import Protocol


@dataclass
class Frame:
    """Container for a captured frame."""
    data: bytes
    encoding: str = "jpeg"


class Camera(Protocol):
    def capture(self) -> Frame:
        ...

    def release(self) -> None:
        ...


class StubCamera:
    """Minimal ok-capture stub that returns placeholder image bytes."""

    def __init__(self, sample_path: pathlib.Path | None = None) -> None:
        self._sample_path = sample_path
        self._fallback_payload = base64.b64decode(
            b"/9j/4AAQSkZJRgABAQEASABIAAD/2wBDABALDA4MChAODQ4SEhQfJCQfIiEhJycnKysyKysvPz8/Pz9FSkNFRkdMT01QUFVVWFhZWl5dXl5mZmZmaWlp/2wBDARESEhMfJCYfJiZkKykpZGRkZGRkZGRkZGRkZGRkZGRkZGRkZGRkZGRkZGRkZGRkZGRkZGRkZGRkZGRkZGRk/8AAEQgAAgACAwEiAAIRAQMRAf/EABQAAQAAAAAAAAAAAAAAAAAAAAX/xAAUEAEAAAAAAAAAAAAAAAAAAAAA/8QAFQEBAQAAAAAAAAAAAAAAAAAAAwT/xAAUEQEAAAAAAAAAAAAAAAAAAAAA/9oADAMBAAIRAxEAPwCfAAf/2Q=="
        )

    def capture(self) -> Frame:
        if self._sample_path and self._sample_path.exists():
            data = self._sample_path.read_bytes()
            encoding = self._sample_path.suffix.lstrip(".") or "jpeg"
            return Frame(data=data, encoding=encoding)
        return Frame(data=self._fallback_payload)

    def release(self) -> None:
        return None


class OpenCVCamera:
    """Capture frames from an OpenCV-compatible source (USB/RTSP)."""

    def __init__(
        self,
        source: int | str = 0,
        *,
        encoding: str = "jpeg",
        resolution: tuple[int, int] | None = None,
        backend: int | None = None,
    ) -> None:
        try:
            import cv2  # type: ignore
        except ImportError as exc:  # pragma: no cover - depends on optional dep
            raise RuntimeError("opencv-python is required for OpenCVCamera") from exc

        self._cv2 = cv2
        self._encoding = encoding.lstrip(".") or "jpeg"
        self._source = source
        self._cap = cv2.VideoCapture(source, backend if backend is not None else cv2.CAP_ANY)
        if not self._cap.isOpened():
            raise RuntimeError(f"Unable to open camera source {source!r}")
        if resolution:
            width, height = resolution
            self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, float(width))
            self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, float(height))

    def capture(self) -> Frame:
        ok, frame = self._cap.read()
        if not ok or frame is None:
            raise RuntimeError("Failed to capture frame from camera")
        success, buffer = self._cv2.imencode(f".{self._encoding}", frame)
        if not success:
            raise RuntimeError(f"OpenCV failed to encode frame as {self._encoding}")
        return Frame(data=buffer.tobytes(), encoding=self._encoding)

    def release(self) -> None:
        if getattr(self, "_cap", None) is not None:
            self._cap.release()
            self._cap = None

    def __del__(self) -> None:  # pragma: no cover - destructor best effort
        try:
            self.release()
        except Exception:
            pass


__all__ = ["Frame", "Camera", "StubCamera", "OpenCVCamera"]