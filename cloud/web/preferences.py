from __future__ import annotations

import json
from pathlib import Path
from typing import List

from pydantic import BaseModel, Field, validator

DEFAULT_CAPTURE_STATES: List[str] = ["normal", "abnormal", "uncertain"]
CAPTURE_LIMIT_DEFAULT = 12
CAPTURE_LIMIT_MAX = 100


class CaptureFilterPreferences(BaseModel):
    states: List[str] = Field(default_factory=lambda: list(DEFAULT_CAPTURE_STATES))
    from_dt: str | None = None
    to_dt: str | None = None
    limit: int = CAPTURE_LIMIT_DEFAULT

    @validator("states", pre=True, always=True)
    def _sanitize_states(cls, value: object) -> List[str]:  # type: ignore[override]
        items: List[str] = []
        if isinstance(value, list):
            for entry in value:
                if not isinstance(entry, str):
                    continue
                normalized = entry.strip().lower()
                if normalized in DEFAULT_CAPTURE_STATES and normalized not in items:
                    items.append(normalized)
        if not items:
            return list(DEFAULT_CAPTURE_STATES)
        return items

    @validator("limit", pre=True, always=True)
    def _clamp_limit(cls, value: object) -> int:  # type: ignore[override]
        try:
            limit = int(value)
        except (TypeError, ValueError):
            return CAPTURE_LIMIT_DEFAULT
        if limit <= 0:
            return CAPTURE_LIMIT_DEFAULT
        return max(1, min(limit, CAPTURE_LIMIT_MAX))


class UIPreferences(BaseModel):
    auto_refresh: bool = True
    capture_filters: CaptureFilterPreferences = Field(
        default_factory=CaptureFilterPreferences
    )


def load_preferences(path: Path) -> UIPreferences:
    if not path.exists():
        return UIPreferences()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return UIPreferences()
    try:
        return UIPreferences.parse_obj(raw)
    except Exception:
        return UIPreferences()


def save_preferences(path: Path, preferences: UIPreferences) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = preferences.model_dump()
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


__all__ = [
    "CAPTURE_LIMIT_DEFAULT",
    "CAPTURE_LIMIT_MAX",
    "DEFAULT_CAPTURE_STATES",
    "CaptureFilterPreferences",
    "UIPreferences",
    "load_preferences",
    "save_preferences",
]
