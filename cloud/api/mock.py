from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

from device.capture import Frame


@dataclass
class Classification:
    state: str
    confidence: float = 0.5


@dataclass
class MockOkApi:
    """Placeholder ok-api that echoes metadata into a classification."""

    default_state: str = "normal"
    records: List[dict[str, str]] = field(default_factory=list)

    def classify(self, frame: Frame, metadata: dict[str, str]) -> dict[str, str]:
        self.records.append(metadata)
        requested = metadata.get("force_state")
        state = (requested or self.default_state).lower()
        confidence = 0.9 if state == "abnormal" else 0.6
        return {"state": state, "confidence": str(confidence)}


__all__ = ["MockOkApi", "Classification"]