from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

# Confidence scores below this threshold are treated as uncertain.
LOW_CONFIDENCE_THRESHOLD: float = 0.6


class Classifier(Protocol):
    def classify(self, image_bytes: bytes) -> "Classification": ...


@dataclass(frozen=True)
class Classification:
    state: str
    score: float
    reason: str | None = None


__all__ = ["Classifier", "Classification", "LOW_CONFIDENCE_THRESHOLD"]
