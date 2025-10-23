from __future__ import annotations

import base64
import os
import time
from dataclasses import dataclass, field
from typing import Any, Dict

import requests

from device.capture import Frame


@dataclass
class OkApiHttpClient:
    base_url: str
    timeout: float = 20.0
    session: requests.Session = field(default_factory=requests.Session)

    def classify(self, frame: Frame, metadata: Dict[str, str]) -> Dict[str, str | None]:
        captured_at = metadata.get("captured_at")

        # Timing debug: Collect device-side timestamps if enabled
        timing_enabled = os.environ.get("ENABLE_TIMING_DEBUG", "").lower() == "true"
        debug_timestamps: Dict[str, float] | None = None

        if timing_enabled:
            debug_timestamps = {}
            # Extract timestamps from frame metadata if available
            if hasattr(frame, 'debug_capture_time'):
                debug_timestamps['t0_device_capture'] = frame.debug_capture_time
            if hasattr(frame, 'debug_thumbnail_time'):
                debug_timestamps['t1_device_thumbnail'] = frame.debug_thumbnail_time
            # Record request send time
            debug_timestamps['t2_device_request_sent'] = time.time()

        payload = {
            "device_id": metadata.get("device_id", "unknown"),
            "trigger_label": metadata.get("trigger_label", "unknown"),
            "image_base64": base64.b64encode(frame.data).decode("ascii"),
            "captured_at": captured_at,
            "metadata": {
                k: v
                for k, v in metadata.items()
                if k not in {"device_id", "trigger_label", "captured_at"}
            },
        }

        # Add timing debug timestamps if enabled
        if debug_timestamps:
            payload["debug_timestamps"] = debug_timestamps

        # Add thumbnail if available
        if frame.thumbnail:
            payload["thumbnail_base64"] = base64.b64encode(frame.thumbnail).decode("ascii")
        try:
            response = self.session.post(
                f"{self.base_url.rstrip('/')}/v1/captures",
                json=payload,
                timeout=self.timeout,
            )
            response.raise_for_status()
            data = response.json()
        except requests.Timeout as exc:  # pragma: no cover - network conditions
            raise RuntimeError("Timed out waiting for classification response") from exc
        except (
            requests.RequestException
        ) as exc:  # pragma: no cover - network conditions
            raise RuntimeError(f"Failed to call OK API: {exc}") from exc
        reason = data.get("reason")
        if reason is not None:
            reason = str(reason)
        return {
            "state": data["state"],
            "confidence": str(data.get("score", 0.0)),
            "reason": reason,
        }


__all__ = ["OkApiHttpClient"]
