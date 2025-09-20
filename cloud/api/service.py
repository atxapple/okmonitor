from __future__ import annotations

import base64
from dataclasses import dataclass
from typing import Any, Dict

from ..ai.simple import Classifier
from ..datalake.storage import FileSystemDatalake


@dataclass
class InferenceService:
    classifier: Classifier
    datalake: FileSystemDatalake

    def process_capture(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        image_b64: str = payload["image_base64"]
        image_bytes = base64.b64decode(image_b64)
        classification = self.classifier.classify(image_bytes)

        metadata = {
            "device_id": payload["device_id"],
            "trigger_label": payload["trigger_label"],
            **payload.get("metadata", {}),
        }
        record = self.datalake.store_capture(
            image_bytes=image_bytes,
            metadata=metadata,
            classification={"state": classification.state, "score": classification.score},
        )
        return {
            "record_id": record.record_id,
            "state": classification.state,
            "score": classification.score,
        }


__all__ = ["InferenceService"]