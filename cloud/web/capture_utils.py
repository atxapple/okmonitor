from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


@dataclass
class CaptureSummary:
    record_id: str
    captured_at: str
    state: str
    score: float
    reason: Optional[str]
    trigger_label: Optional[str]
    image_path: Optional[Path]
    captured_at_dt: Optional[datetime]


def parse_capture_timestamp(value: str | None) -> datetime | None:
    if value is None:
        return None

    text = str(value).strip()
    if not text:
        return None

    if " " in text and "T" not in text:
        text = text.replace(" ", "T", 1)

    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"

    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)

    return parsed


def find_capture_image(json_path: Path) -> Optional[Path]:
    for ext in (".jpeg", ".jpg", ".png"):
        candidate = json_path.with_suffix(ext)
        if candidate.exists():
            return candidate
    return None


def load_capture_summary(json_path: Path) -> Optional[CaptureSummary]:
    try:
        payload = json.loads(json_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None

    classification = payload.get("classification", {})
    metadata = payload.get("metadata", {})

    raw_state = classification.get("state", "unknown")
    state = str(raw_state).strip().lower()

    score_value = classification.get("score", 0.0)
    try:
        score = float(score_value)
    except (TypeError, ValueError):
        score = 0.0

    reason_value = classification.get("reason")
    reason = None
    if isinstance(reason_value, str):
        reason = reason_value.strip() or None
    elif reason_value is not None:
        reason = str(reason_value)

    captured_at_raw = payload.get("captured_at", "")
    captured_at_dt = parse_capture_timestamp(captured_at_raw)

    image_path = find_capture_image(json_path)

    return CaptureSummary(
        record_id=str(payload.get("record_id", json_path.stem)),
        captured_at=str(captured_at_raw),
        state=state,
        score=score,
        reason=reason,
        trigger_label=metadata.get("trigger_label"),
        image_path=image_path,
        captured_at_dt=captured_at_dt,
    )


__all__ = [
    "CaptureSummary",
    "find_capture_image",
    "load_capture_summary",
    "parse_capture_timestamp",
]
