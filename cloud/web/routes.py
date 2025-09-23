from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, List, Optional, Sequence, Set

from fastapi import APIRouter, HTTPException, Query, Request
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
    captured_at_dt: Optional[datetime]


_ALLOWED_CAPTURE_STATES: Set[str] = {"normal", "abnormal", "unexpected"}
_MAX_CAPTURE_LIMIT = 100


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
    manual_counter = getattr(request.app.state, "manual_trigger_counter", 0)
    return {
        "normal_description": normal_description,
        "classifier": classifier_name,
        "device_id": device_id,
        "manual_trigger_counter": manual_counter,
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
async def list_captures(
    request: Request,
    limit: int = 12,
    state: list[str] | None = Query(default=None),
    start: str | None = Query(default=None, alias="from"),
    end: str | None = Query(default=None, alias="to"),
) -> List[dict[str, Any]]:
    states, states_explicit = _normalize_state_filters(state)
    start_dt = _parse_filter_datetime(start)
    end_dt = _parse_filter_datetime(end)
    if start_dt and end_dt and start_dt > end_dt:
        raise HTTPException(status_code=400, detail="'from' value must be before 'to'")

    clamped_limit = max(0, min(limit, _MAX_CAPTURE_LIMIT))
    if clamped_limit == 0:
        return []

    if states_explicit and states is not None and not states:
        return []

    datalake_root: Path | None = getattr(request.app.state, "datalake_root", None)
    if datalake_root is None or not datalake_root.exists():
        return []

    summaries = _collect_recent_captures(
        datalake_root,
        clamped_limit,
        states=states,
        start=start_dt,
        end=end_dt,
    )
    captures: List[dict[str, Any]] = []
    for summary in summaries:
        image_url = None
        if summary.image_path is not None:
            image_url = str(request.url_for("serve_capture_image", record_id=summary.record_id))
        download_url = f"{image_url}?download=1" if image_url else None
        captures.append(
            {
                "record_id": summary.record_id,
                "captured_at": summary.captured_at,
                "state": summary.state,
                "score": summary.score,
                "reason": summary.reason,
                "trigger_label": summary.trigger_label,
                "image_url": image_url,
                "download_url": download_url,
            }
        )
    return captures


@router.get("/ui/captures/{record_id}/image")
async def serve_capture_image(record_id: str, request: Request, download: bool = False) -> FileResponse:
    datalake_root: Path | None = getattr(request.app.state, "datalake_root", None)
    if datalake_root is None:
        raise HTTPException(status_code=404, detail="Capture not found")

    json_path = _find_capture_json(datalake_root, record_id)
    if json_path is None:
        raise HTTPException(status_code=404, detail="Capture not found")

    image_path = _find_capture_image(json_path)
    if image_path is None:
        raise HTTPException(status_code=404, detail="Capture image missing")

    filename = image_path.name if download else None
    return FileResponse(image_path, filename=filename)


def _collect_recent_captures(
    root: Path,
    limit: int,
    *,
    states: Set[str] | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
) -> List[CaptureSummary]:
    if limit <= 0:
        return []

    json_files = sorted(root.glob("**/*.json"), key=lambda path: path.stat().st_mtime, reverse=True)
    matches: list[tuple[datetime, CaptureSummary]] = []

    for path in json_files:
        if len(matches) >= limit:
            break
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue

        classification = payload.get("classification", {})
        metadata = payload.get("metadata", {})
        state_value = str(classification.get("state", "unknown")).lower()

        if states is not None and state_value not in states:
            continue

        captured_at_raw = payload.get("captured_at", "")
        captured_at_dt = _parse_filter_datetime(captured_at_raw)

        if start is not None and (captured_at_dt is None or captured_at_dt < start):
            continue
        if end is not None and (captured_at_dt is None or captured_at_dt > end):
            continue

        try:
            mtime = path.stat().st_mtime
        except OSError:
            mtime = 0.0
        fallback_dt = datetime.fromtimestamp(mtime, tz=timezone.utc)
        sort_key = captured_at_dt or fallback_dt

        summary = CaptureSummary(
            record_id=payload.get("record_id", path.stem),
            captured_at=captured_at_raw,
            state=state_value,
            score=float(classification.get("score", 0.0) or 0.0),
            reason=classification.get("reason"),
            trigger_label=metadata.get("trigger_label"),
            image_path=_find_capture_image(path),
            captured_at_dt=captured_at_dt,
        )

        matches.append((sort_key, summary))

    matches.sort(key=lambda item: item[0], reverse=True)
    return [summary for _, summary in matches[:limit]]


def _normalize_state_filters(values: Sequence[str] | None) -> tuple[Set[str] | None, bool]:
    if values is None:
        return None, False

    normalized = [str(value).strip().lower() for value in values if value is not None]
    valid = {value for value in normalized if value in _ALLOWED_CAPTURE_STATES}
    if valid:
        return valid, True

    if normalized:
        return set(), True

    return set(), True


def _parse_filter_datetime(value: str | None) -> datetime | None:
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




