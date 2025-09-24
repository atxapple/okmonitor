from __future__ import annotations

import base64
import logging
from dataclasses import dataclass
from typing import Any, Dict

from ..ai import Classifier
from ..datalake.storage import FileSystemDatalake
from .capture_index import RecentCaptureIndex


logger = logging.getLogger(__name__)


@dataclass
class InferenceService:
    classifier: Classifier
    datalake: FileSystemDatalake
    capture_index: RecentCaptureIndex | None = None

    def process_capture(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        image_b64: str = payload["image_base64"]
        try:
            image_bytes = base64.b64decode(image_b64)
        except Exception as exc:
            logger.exception("Failed to decode image payload: %s", exc)
            raise RuntimeError("Invalid base64 image payload") from exc

        logger.info(
            "Running inference device=%s trigger=%s image_bytes=%d",
            payload.get("device_id"),
            payload.get("trigger_label"),
            len(image_bytes),
        )

        classification = self.classifier.classify(image_bytes)
        logger.info(
            "Inference complete device=%s state=%s score=%.2f",
            payload.get("device_id"),
            classification.state,
            classification.score,
        )

        metadata = {
            "device_id": payload["device_id"],
            "trigger_label": payload["trigger_label"],
            **payload.get("metadata", {}),
        }
        classification_payload = {
            "state": classification.state,
            "score": classification.score,
            "reason": classification.reason,
        }
        record = self.datalake.store_capture(
            image_bytes=image_bytes,
            metadata=metadata,
            classification=classification_payload,
        )
        if self.capture_index is not None:
            self.capture_index.add_record(record)
        logger.debug(
            "Stored capture record_id=%s metadata_keys=%s",
            record.record_id,
            sorted(metadata.keys()),
        )
        return {
            "record_id": record.record_id,
            **classification_payload,
        }


__all__ = ["InferenceService"]
