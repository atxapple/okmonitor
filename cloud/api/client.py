from __future__ import annotations

import base64
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
        payload = {
            "device_id": metadata.get("device_id", "unknown"),
            "trigger_label": metadata.get("trigger_label", "unknown"),
            "image_base64": base64.b64encode(frame.data).decode("ascii"),
            "metadata": {k: v for k, v in metadata.items() if k not in {"device_id", "trigger_label"}},
        }
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
        except requests.RequestException as exc:  # pragma: no cover - network conditions
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
