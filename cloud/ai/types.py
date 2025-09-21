from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class Classifier(Protocol):
    def classify(self, image_bytes: bytes) -> "Classification":
        ...


@dataclass(frozen=True)
class Classification:
    state: str
    score: float
    reason: str | None = None


__all__ = ["Classifier", "Classification"]
