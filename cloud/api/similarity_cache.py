from __future__ import annotations

import json
import threading
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional


@dataclass
class CachedEvaluation:
    device_id: str
    record_id: str
    hash_hex: str
    state: str
    score: float
    reason: str | None
    captured_at: str

    def is_expired(self, expiry_minutes: float, *, now: datetime | None = None) -> bool:
        if expiry_minutes <= 0:
            return False
        try:
            captured = datetime.fromisoformat(self.captured_at)
        except ValueError:
            return True
        if captured.tzinfo is None:
            captured = captured.replace(tzinfo=timezone.utc)
        now = now or datetime.now(timezone.utc)
        delta = now - captured
        return delta.total_seconds() > expiry_minutes * 60


class SimilarityCache:
    """Persistence layer for reuse of recent classifications."""

    def __init__(self, path: Path | None = None) -> None:
        self._path = path
        self._lock = threading.Lock()
        self._entries: Dict[str, CachedEvaluation] = {}
        if self._path is not None:
            self._load()

    def _load(self) -> None:
        if self._path is None or not self._path.exists():
            return
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        for device_id, payload in data.items():
            if not isinstance(payload, dict):
                continue
            try:
                entry = CachedEvaluation(
                    device_id=device_id,
                    record_id=str(payload["record_id"]),
                    hash_hex=str(payload["hash_hex"]),
                    state=str(payload["state"]),
                    score=float(payload.get("score", 0.0)),
                    reason=payload.get("reason"),
                    captured_at=str(payload["captured_at"]),
                )
            except (KeyError, ValueError, TypeError):
                continue
            self._entries[device_id] = entry

    def _save(self) -> None:
        if self._path is None:
            return
        payload = {
            device_id: asdict(entry) for device_id, entry in self._entries.items()
        }
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.write_text(
                json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8"
            )
        except OSError:
            # Cache persistence is best-effort; ignore failures.
            pass

    def get(self, device_id: str) -> Optional[CachedEvaluation]:
        with self._lock:
            return self._entries.get(device_id)

    def update(
        self,
        *,
        device_id: str,
        record_id: str,
        hash_hex: str,
        state: str,
        score: float,
        reason: str | None,
        captured_at: datetime | None = None,
    ) -> None:
        captured = captured_at or datetime.now(timezone.utc)
        entry = CachedEvaluation(
            device_id=device_id,
            record_id=record_id,
            hash_hex=hash_hex,
            state=state,
            score=score,
            reason=reason,
            captured_at=captured.astimezone(timezone.utc).isoformat(),
        )
        with self._lock:
            self._entries[device_id] = entry
            self._save()

    def prune_expired(self, expiry_minutes: float) -> None:
        if expiry_minutes <= 0:
            return
        now = datetime.now(timezone.utc)
        with self._lock:
            expired = [
                device_id
                for device_id, entry in self._entries.items()
                if entry.is_expired(expiry_minutes, now=now)
            ]
            for device_id in expired:
                self._entries.pop(device_id, None)
            if expired:
                self._save()


__all__ = ["SimilarityCache", "CachedEvaluation"]
