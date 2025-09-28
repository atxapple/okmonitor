from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from threading import Lock
from typing import List, Optional

from ..datalake.storage import CaptureRecord
from ..web.capture_utils import CaptureSummary, load_capture_summary


class RecentCaptureIndex:
    """Maintain an in-memory list of the most recent capture summaries."""

    def __init__(self, root: Path, max_items: int = 500) -> None:
        self._root = root
        self._max_items = max_items
        self._lock = Lock()
        self._entries: List[CaptureSummary] = []
        self._load_initial()

    def _load_initial(self) -> None:
        if not self._root.exists():
            return

        json_paths = sorted(
            self._root.glob("**/*.json"),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )[: self._max_items]

        for path in json_paths:
            summary = load_capture_summary(path)
            if summary is None:
                continue
            self._entries.append(summary)

    def add_record(self, record: CaptureRecord) -> None:
        summary = CaptureSummary(
            record_id=record.record_id,
            captured_at=record.captured_at.isoformat(),
            state=_normalize_state(record.classification.get("state")),
            score=_normalize_score(record.classification.get("score")),
            reason=_normalize_reason(record.classification.get("reason")),
            trigger_label=record.metadata.get("trigger_label"),
            normal_description_file=record.normal_description_file,
            image_path=record.image_path if record.image_path.exists() else None,
            captured_at_dt=record.captured_at,
        )
        with self._lock:
            self._entries.insert(0, summary)
            if len(self._entries) > self._max_items:
                del self._entries[self._max_items :]

    def latest(self, limit: int) -> List[CaptureSummary]:
        if limit <= 0:
            return []
        with self._lock:
            window = self._entries[:limit]
        return [replace(entry) for entry in window]


def _normalize_state(value: object) -> str:
    if isinstance(value, str):
        text = value.strip().lower()
        return text or "unknown"
    return "unknown"


def _normalize_score(value: object) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _normalize_reason(value: object) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, str):
        text = value.strip()
        return text or None
    return str(value)


__all__ = ["RecentCaptureIndex"]
