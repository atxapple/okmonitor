from __future__ import annotations

from dataclasses import dataclass
import base64
import pathlib
from typing import Protocol


def create_thumbnail(image_bytes: bytes, max_size: tuple[int, int] = (400, 300), quality: int = 85) -> bytes:
    """Create a thumbnail from image bytes.

    Args:
        image_bytes: Original image data
        max_size: Maximum dimensions (width, height) for thumbnail
        quality: JPEG quality (0-100)

    Returns:
        Thumbnail image bytes
    """
    try:
        import cv2
        import numpy as np
    except ImportError:
        # If OpenCV not available, return original (graceful degradation)
        return image_bytes

    # Decode image
    nparr = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if img is None:
        return image_bytes

    # Calculate thumbnail size maintaining aspect ratio
    h, w = img.shape[:2]
    max_w, max_h = max_size

    # Calculate scaling factor
    scale = min(max_w / w, max_h / h)
    if scale >= 1.0:
        # Image is already smaller than thumbnail size
        return image_bytes

    new_w = int(w * scale)
    new_h = int(h * scale)

    # Resize image
    thumbnail = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_AREA)

    # Encode as JPEG with specified quality
    encode_params = [cv2.IMWRITE_JPEG_QUALITY, quality]
    success, buffer = cv2.imencode('.jpg', thumbnail, encode_params)

    if not success:
        return image_bytes

    return buffer.tobytes()


@dataclass
class Frame:
    """Container for a captured frame."""

    data: bytes
    encoding: str = "jpeg"
    thumbnail: bytes | None = None  # Optional thumbnail (smaller version)
    # Timing debug fields (populated when ENABLE_TIMING_DEBUG=true)
    debug_capture_time: float | None = None  # Timestamp when capture() was called
    debug_thumbnail_time: float | None = None  # Timestamp after thumbnail created


class Camera(Protocol):
    def capture(self) -> Frame: ...

    def release(self) -> None: ...


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

    _BACKEND_ALIASES = {
        "any": "CAP_ANY",
        "auto": "CAP_ANY",
        "dshow": "CAP_DSHOW",
        "directshow": "CAP_DSHOW",
        "msmf": "CAP_MSMF",
        "mediafoundation": "CAP_MSMF",
        "vfw": "CAP_VFW",
        "opencv": "CAP_ANY",
    }

    def __init__(
        self,
        source: int | str = 0,
        *,
        encoding: str = "jpeg",
        resolution: tuple[int, int] | None = None,
        backend: str | int | None = None,
        warmup_frames: int = 2,
    ) -> None:
        try:
            import cv2  # type: ignore
        except ImportError as exc:  # pragma: no cover - depends on optional dep
            raise RuntimeError("opencv-python is required for OpenCVCamera") from exc

        self._cv2 = cv2
        self._encoding = encoding.lstrip(".") or "jpeg"
        self._source = source
        self._cap = cv2.VideoCapture(source, self._resolve_backend(backend, cv2))
        if not self._cap.isOpened():
            raise RuntimeError(f"Unable to open camera source {source!r}")
        if resolution:
            width, height = resolution
            self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, float(width))
            self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, float(height))
        if warmup_frames > 0:
            self._warmup(warmup_frames)

    def _resolve_backend(self, backend: str | int | None, cv2_module) -> int:
        if backend is None:
            return cv2_module.CAP_ANY
        if isinstance(backend, int):
            return backend
        key = backend.strip().lower()
        attr_name = self._BACKEND_ALIASES.get(key)
        if attr_name is None:
            raise ValueError(f"Unknown OpenCV backend alias: {backend!r}")
        return getattr(cv2_module, attr_name, cv2_module.CAP_ANY)

    def _warmup(self, warmup_frames: int) -> None:
        for _ in range(warmup_frames):
            ok, _ = self._cap.read()
            if not ok:
                break

    def capture(self, flush_buffer_frames: int = 30) -> Frame:
        import os
        import time

        # Timing debug: Record capture start time
        timing_enabled = os.environ.get("ENABLE_TIMING_DEBUG", "").lower() == "true"
        t0 = time.time() if timing_enabled else None

        # Flush camera buffer to get the freshest frame possible
        # USB cameras buffer many frames internally, causing severe lag (20-30 seconds)
        # We rapidly read and discard frames to clear the buffer
        for _ in range(flush_buffer_frames):
            self._cap.grab()  # Grab frame from buffer without decoding (faster)

        # Now read the actual frame we want (should be the freshest available)
        ok, frame = self._cap.read()
        if not ok or frame is None:
            raise RuntimeError("Failed to capture frame from camera")
        success, buffer = self._cv2.imencode(f".{self._encoding}", frame)
        if not success:
            raise RuntimeError(f"OpenCV failed to encode frame as {self._encoding}")

        # Generate full image bytes
        full_image = buffer.tobytes()

        # Generate thumbnail
        thumbnail = create_thumbnail(full_image, max_size=(400, 300), quality=85)

        # Timing debug: Record thumbnail complete time
        t1 = time.time() if timing_enabled else None

        return Frame(
            data=full_image,
            encoding=self._encoding,
            thumbnail=thumbnail,
            debug_capture_time=t0,
            debug_thumbnail_time=t1,
        )

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
