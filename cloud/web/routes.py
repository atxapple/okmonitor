from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, List, Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(tags=["ui"])

INDEX_HTML = Path(__file__).parent / "templates" / "index.html"


class NormalDescriptionPayload(BaseModel):
    description: str = Field(default="", description="Updated normal environment description")


class TriggerConfigPayload(BaseModel):
    enabled: bool
    interval_seconds: Optional[float] = Field(default=None, ge=1.0, description="Interval in seconds")


@dataclass
class CaptureSummary:
    record_id: str
    captured_at: str
    state: str
    score: float
    reason: Optional[str]
    trigger_label: Optional[str]
    image_path: Optional[Path]


@router.get("/ui", response_class=HTMLResponse)
async def ui_root() -> HTMLResponse:
    if not INDEX_HTML.exists():
        raise HTTPException(status_code=500, detail="UI template missing")
    return HTMLResponse(INDEX_HTML.read_text(encoding="utf-8"))


@router.get("/ui/state")
async def ui_state(request: Request) -> dict[str, Any]:
    config_state = getattr(request.app.state, "trigger_config", None)
    enabled = getattr(config_state, "enabled", False)
    interval = getattr(config_state, "interval_seconds", None)
    normal_description: str = getattr(request.app.state, "normal_description", "")
    classifier = getattr(request.app.state, "classifier", None)
    classifier_name = classifier.__class__.__name__ if classifier else "unknown"
    device_id = getattr(request.app.state, "device_id", "ui-device")
    return {
        "normal_description": normal_description,
        "classifier": classifier_name,
        "device_id": device_id,
        "trigger": {
            "enabled": enabled,
            "interval_seconds": interval,
        },
    }


@router.post("/ui/normal-description")
async def update_normal_description(payload: NormalDescriptionPayload, request: Request) -> dict[str, Any]:
    description = payload.description.strip()
    request.app.state.normal_description = description

    classifier = getattr(request.app.state, "classifier", None)
    if classifier is not None and hasattr(classifier, "normal_description"):
        setattr(classifier, "normal_description", description)

    description_path = getattr(request.app.state, "normal_description_path", None)
    if description_path:
        path = Path(description_path)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(description, encoding="utf-8")
        except OSError as exc:  # pragma: no cover - filesystem error surfaced to client
            raise HTTPException(status_code=500, detail=f"Failed to persist description: {exc}") from exc

    return {"normal_description": description}


@router.post("/ui/trigger")
async def update_trigger(payload: TriggerConfigPayload, request: Request) -> dict[str, Any]:
    config_state = getattr(request.app.state, "trigger_config", None)

    if payload.enabled and (payload.interval_seconds is None or payload.interval_seconds <= 0):
        raise HTTPException(status_code=400, detail="Interval must be provided and greater than zero")

    if hasattr(config_state, "enabled"):
        config_state.enabled = payload.enabled
        config_state.interval_seconds = payload.interval_seconds if payload.enabled else None
        enabled = config_state.enabled
        interval = config_state.interval_seconds
    else:
        config_state = {
            "enabled": payload.enabled,
            "interval_seconds": payload.interval_seconds if payload.enabled else None,
        }
        request.app.state.trigger_config = config_state
        enabled = config_state["enabled"]
        interval = config_state["interval_seconds"]

    return {
        "trigger": {
            "enabled": enabled,
            "interval_seconds": interval,
        }
    }


@router.get("/ui/captures")
async def list_captures(request: Request, limit: int = 12) -> List[dict[str, Any]]:
    datalake_root: Path | None = getattr(request.app.state, "datalake_root", None)
    if datalake_root is None or not datalake_root.exists():
        return []

    summaries = _collect_recent_captures(datalake_root, limit)
    captures: List[dict[str, Any]] = []
    for summary in summaries:
        image_url = None
        if summary.image_path is not None:
            image_url = str(request.url_for("serve_capture_image", record_id=summary.record_id))
        captures.append(
            {
                "record_id": summary.record_id,
                "captured_at": summary.captured_at,
                "state": summary.state,
                "score": summary.score,
                "reason": summary.reason,
                "trigger_label": summary.trigger_label,
                "image_url": image_url,
            }
        )
    return captures


@router.get("/ui/captures/{record_id}/image")
async def serve_capture_image(record_id: str, request: Request) -> FileResponse:
    datalake_root: Path | None = getattr(request.app.state, "datalake_root", None)
    if datalake_root is None:
        raise HTTPException(status_code=404, detail="Capture not found")

    json_path = _find_capture_json(datalake_root, record_id)
    if json_path is None:
        raise HTTPException(status_code=404, detail="Capture not found")

    image_path = _find_capture_image(json_path)
    if image_path is None:
        raise HTTPException(status_code=404, detail="Capture image missing")

    return FileResponse(image_path)


def _collect_recent_captures(root: Path, limit: int) -> List[CaptureSummary]:
    json_files = sorted(root.glob("**/*.json"), key=lambda path: path.stat().st_mtime, reverse=True)
    summaries: List[CaptureSummary] = []
    for path in json_files[:limit]:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        classification = payload.get("classification", {})
        metadata = payload.get("metadata", {})
        summaries.append(
            CaptureSummary(
                record_id=payload.get("record_id", path.stem),
                captured_at=payload.get("captured_at", ""),
                state=str(classification.get("state", "unknown")).lower(),
                score=float(classification.get("score", 0.0) or 0.0),
                reason=classification.get("reason"),
                trigger_label=metadata.get("trigger_label"),
                image_path=_find_capture_image(path),
            )
        )
    return summaries


def _find_capture_json(root: Path, record_id: str) -> Optional[Path]:
    pattern = f"**/{record_id}.json"
    for path in root.glob(pattern):
        if path.is_file():
            return path
    return None


def _find_capture_image(json_path: Path) -> Optional[Path]:
    for ext in (".jpeg", ".jpg", ".png"):
        candidate = json_path.with_suffix(ext)
        if candidate.exists():
            return candidate
    return None


__all__ = ["router"]
