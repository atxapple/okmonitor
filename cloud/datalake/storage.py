from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict
import uuid


@dataclass
class CaptureRecord:
    record_id: str
    image_path: Path
    metadata_path: Path
    captured_at: datetime
    metadata: Dict[str, Any]
    classification: Dict[str, Any]
    normal_description_file: str | None = None


class FileSystemDatalake:
    """Store captures on the local filesystem."""

    def __init__(self, root: Path) -> None:
        self._root = root
        self._root.mkdir(parents=True, exist_ok=True)

    @property
    def root(self) -> Path:
        return self._root

    def store_capture(
        self,
        image_bytes: bytes,
        metadata: Dict[str, Any],
        classification: Dict[str, Any],
        *,
        normal_description_file: str | None = None,
    ) -> CaptureRecord:
        timestamp = datetime.now(tz=timezone.utc)
        date_dir = self._root / timestamp.strftime("%Y/%m/%d")
        date_dir.mkdir(parents=True, exist_ok=True)

        record_id = uuid.uuid4().hex
        image_path = date_dir / f"{record_id}.jpeg"
        metadata_path = date_dir / f"{record_id}.json"

        image_path.write_bytes(image_bytes)
        payload = {
            "record_id": record_id,
            "captured_at": timestamp.isoformat(),
            "metadata": metadata,
            "classification": classification,
            "normal_description_file": normal_description_file,
        }
        metadata_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return CaptureRecord(
            record_id=record_id,
            image_path=image_path,
            metadata_path=metadata_path,
            captured_at=timestamp,
            metadata=metadata,
            classification=classification,
            normal_description_file=normal_description_file,
        )


__all__ = ["CaptureRecord", "FileSystemDatalake"]
