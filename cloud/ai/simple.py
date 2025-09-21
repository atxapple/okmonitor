from __future__ import annotations

import io
from dataclasses import dataclass

from PIL import Image, ImageStat

from .types import Classification, Classifier


@dataclass
class SimpleThresholdModel:
    """Baseline anomaly detector using grayscale intensity."""

    threshold: float = 0.65

    def classify(self, image_bytes: bytes) -> Classification:
        image = Image.open(io.BytesIO(image_bytes)).convert("L")
        stats = ImageStat.Stat(image)
        avg_luma = stats.mean[0] / 255.0
        score = float(max(0.0, min(1.0, avg_luma)))
        state = "abnormal" if score >= self.threshold else "normal"
        reason = None
        if state == "abnormal":
            reason = f"Average luma {score:.2f} exceeds threshold {self.threshold:.2f}."
        return Classification(state=state, score=score, reason=reason)


__all__ = ["Classification", "Classifier", "SimpleThresholdModel"]
