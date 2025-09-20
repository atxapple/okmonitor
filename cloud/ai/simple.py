from __future__ import annotations

import io
from dataclasses import dataclass
from statistics import mean
from typing import Protocol

from PIL import Image, ImageStat


class Classifier(Protocol):
    def classify(self, image_bytes: bytes) -> "Classification":
        ...


@dataclass(frozen=True)
class Classification:
    state: str
    score: float


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
        return Classification(state=state, score=score)


__all__ = ["Classification", "Classifier", "SimpleThresholdModel"]