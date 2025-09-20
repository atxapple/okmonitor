from __future__ import annotations

import base64
from dataclasses import dataclass, field
from typing import Any, Dict

import requests

from device.capture import Frame


@dataclass
class OkApiHttpClient:
    base_url: str
    timeout: float = 5.0
    session: requests.Session = field(default_factory=requests.Session)

    def classify(self, frame: Frame, metadata: Dict[str, str]) -> Dict[str, str]:
        payload = {
            "device_id": metadata.get("device_id", "unknown"),
            "trigger_label": metadata.get("trigger_label", "unknown"),
            "image_base64": base64.b64encode(frame.data).decode("ascii"),
            "metadata": {k: v for k, v in metadata.items() if k not in {"device_id", "trigger_label"}},
        }
        response = self.session.post(
            f"{self.base_url.rstrip('/')}/v1/captures",
            json=payload,
            timeout=self.timeout,
        )
        response.raise_for_status()
        data = response.json()
        return {"state": data["state"], "confidence": str(data.get("score", 0.0))}


__all__ = ["OkApiHttpClient"]