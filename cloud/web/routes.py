from __future__ import annotations

import re


import logging
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, List, Optional, Sequence, Set

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel, Field

from ..api.email_service import create_sendgrid_service
from ..api.notification_settings import NotificationSettings, save_notification_settings
from .capture_utils import (
    CaptureSummary,
    find_capture_image,
    load_capture_summary,
    parse_capture_timestamp,
)


logger = logging.getLogger(__name__)

router = APIRouter(tags=["ui"])

INDEX_HTML = Path(__file__).parent / "templates" / "index.html"


MIN_TRIGGER_INTERVAL_SECONDS = 10.0


class NormalDescriptionPayload(BaseModel):
    description: str = Field(default="", description="Updated normal environment description")


class TriggerConfigPayload(BaseModel):
    enabled: bool
    interval_seconds: Optional[float] = Field(
        default=None,
        ge=MIN_TRIGGER_INTERVAL_SECONDS,
        description="Interval in seconds",
    )


class NotificationSettingsPayload(BaseModel):
    email_enabled: bool
    email_recipients: List[str] = Field(default_factory=list, description="Notification email recipients")



_ALLOWED_CAPTURE_STATES: Set[str] = {"normal", "abnormal", "uncertain"}
_MAX_CAPTURE_LIMIT = 100
_EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


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
    last_seen = getattr(request.app.state, "device_last_seen", None)
    last_ip = getattr(request.app.state, "device_last_ip", None)
    ttl_seconds = float(getattr(request.app.state, "device_status_ttl", 30.0))
    now = datetime.now(timezone.utc)
    connected = False
    last_seen_iso: str | None = None
    if isinstance(last_seen, datetime):
        if now - last_seen <= timedelta(seconds=ttl_seconds):
            connected = True
        last_seen_iso = last_seen.isoformat()
    notification_settings: NotificationSettings = getattr(request.app.state, "notification_settings", NotificationSettings())
    notifications_payload = {
        "email": {
            "enabled": bool(notification_settings.email.enabled),
            "recipients": list(notification_settings.email.recipients),
        }
    }
    return {
        "normal_description": normal_description,
        "normal_description_file": getattr(request.app.state, "normal_description_file", None),
        "classifier": classifier_name,
        "device_id": device_id,
        "manual_trigger_counter": manual_counter,
        "trigger": {
            "enabled": enabled,
            "interval_seconds": interval,
        },
        "device_status": {
            "connected": connected,
            "last_seen": last_seen_iso,
            "ip": last_ip,
            "ttl_seconds": ttl_seconds,
        },
        "notifications": notifications_payload,
    }


@router.post("/ui/normal-description")
async def update_normal_description(payload: NormalDescriptionPayload, request: Request) -> dict[str, Any]:
    description = payload.description.strip()
    request.app.state.normal_description = description

    classifier = getattr(request.app.state, "classifier", None)
    _apply_normal_description(classifier, description)

    store_dir = getattr(request.app.state, "normal_description_store_dir", None)
    store_dir_path = Path(store_dir) if store_dir else Path("config/normal_descriptions")
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    file_suffix = uuid.uuid4().hex[:8]
    file_name = f"normal_{timestamp}_{file_suffix}.txt"
    target_path = store_dir_path / file_name
    try:
        store_dir_path.mkdir(parents=True, exist_ok=True)
        target_path.write_text(description, encoding="utf-8")
    except OSError as exc:  # pragma: no cover - filesystem error surfaced to client
        raise HTTPException(status_code=500, detail=f"Failed to persist description: {exc}") from exc

    request.app.state.normal_description_path = target_path
    request.app.state.normal_description_store_dir = store_dir_path
    request.app.state.normal_description_file = file_name
    service = getattr(request.app.state, "service", None)
    if service is not None:
        service.normal_description_file = file_name

    return {"normal_description": description, "normal_description_file": file_name}


@router.post("/ui/trigger")
async def update_trigger(payload: TriggerConfigPayload, request: Request) -> dict[str, Any]:
    config_state = getattr(request.app.state, "trigger_config", None)

    if payload.enabled and (payload.interval_seconds is None or payload.interval_seconds < MIN_TRIGGER_INTERVAL_SECONDS):
        raise HTTPException(
            status_code=400,
            detail=f"Interval must be at least {MIN_TRIGGER_INTERVAL_SECONDS:.0f} seconds",
        )

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


@router.post("/ui/notifications")
async def update_notifications(payload: NotificationSettingsPayload, request: Request) -> dict[str, Any]:
    recipients = [value.strip() for value in payload.email_recipients if isinstance(value, str)]
    recipients = [value for value in recipients if value]

    if payload.email_enabled and not recipients:
        raise HTTPException(status_code=400, detail="Provide at least one email recipient to enable notifications.")

    invalid = [value for value in recipients if not _EMAIL_PATTERN.match(value)]
    if invalid:
        human_list = ', '.join(invalid)
        raise HTTPException(
            status_code=400,
            detail=f"Invalid email address(es): {human_list}",
        )

    settings: NotificationSettings = getattr(request.app.state, "notification_settings", NotificationSettings())
    store_dir = getattr(request.app.state, "normal_description_store_dir", None)
    store_dir_path = Path(store_dir) if store_dir else Path("config/normal_descriptions")
    settings.email.enabled = payload.email_enabled
    settings.email.recipients = recipients
    sanitized = settings.sanitized()

    base_config = getattr(request.app.state, "email_base_config", None)
    if sanitized.email.enabled and not base_config:
        raise HTTPException(
            status_code=400,
            detail="SendGrid credentials are not configured; email notifications cannot be enabled.",
        )

    notifier = None
    if sanitized.email.enabled and base_config:
        try:
            notifier = create_sendgrid_service(
                api_key=base_config["api_key"],
                sender=base_config["sender"],
                recipients=sanitized.email.recipients,
                environment_label=base_config.get("environment_label"),
                description_root=store_dir_path,
                ui_base_url=base_config.get("ui_base_url"),
            )
        except Exception as exc:  # pragma: no cover - external client init
            logger.exception("Failed to initialise SendGrid client during notification update: %s", exc)
            raise HTTPException(status_code=500, detail="Failed to initialise SendGrid client") from exc

    config_path = getattr(request.app.state, "notification_config_path", None)
    if isinstance(config_path, Path):
        try:
            save_notification_settings(config_path, sanitized)
        except OSError as exc:  # pragma: no cover - filesystem error surfaced to client
            raise HTTPException(status_code=500, detail=f"Failed to persist notification settings: {exc}") from exc

    request.app.state.notification_settings = sanitized
    request.app.state.abnormal_notifier = notifier
    service = getattr(request.app.state, "service", None)
    if service is not None:
        service.notifier = notifier

    return {
        "notifications": {
            "email": {
                "enabled": sanitized.email.enabled,
                "recipients": sanitized.email.recipients,
            }
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
    start_dt = parse_capture_timestamp(start)
    end_dt = parse_capture_timestamp(end)

    if start and start.strip() and start_dt is None:
        raise HTTPException(status_code=400, detail="'from' must be an ISO 8601 timestamp with timezone")
    if end and end.strip() and end_dt is None:
        raise HTTPException(status_code=400, detail="'to' must be an ISO 8601 timestamp with timezone")
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

    capture_index = getattr(request.app.state, "capture_index", None)
    summaries: List[CaptureSummary] = []
    use_index = (
        capture_index is not None
        and not states_explicit
        and start_dt is None
        and end_dt is None
    )

    if use_index:
        summaries = capture_index.latest(clamped_limit)
        if len(summaries) < clamped_limit:
            exclude_ids = {summary.record_id for summary in summaries}
            remaining = clamped_limit - len(summaries)
            if remaining > 0:
                summaries.extend(
                    _collect_recent_captures(
                        datalake_root,
                        remaining,
                        states=states,
                        start=start_dt,
                        end=end_dt,
                        exclude_ids=exclude_ids,
                    )
                )
    else:
        summaries = _collect_recent_captures(
            datalake_root,
            clamped_limit,
            states=states,
            start=start_dt,
            end=end_dt,
        )

    sort_anchor = datetime.fromtimestamp(0, tz=timezone.utc)
    summaries.sort(key=lambda item: item.captured_at_dt or sort_anchor, reverse=True)
    summaries = summaries[:clamped_limit]

    captures: List[dict[str, Any]] = []
    for summary in summaries:
        image_url = None
        if summary.image_path is not None:
            image_route = request.url_for("serve_capture_image", record_id=summary.record_id)
            image_url = image_route.path or str(image_route)
        download_url = f"{image_url}?download=1" if image_url else None
        captures.append(
            {
                "record_id": summary.record_id,
                "captured_at": summary.captured_at,
                "state": summary.state,
                "score": summary.score,
                "reason": summary.reason,
                "trigger_label": summary.trigger_label,
                "normal_description_file": summary.normal_description_file,
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

    image_path = find_capture_image(json_path)
    if image_path is None:
        raise HTTPException(status_code=404, detail="Capture image missing")

    filename = image_path.name if download else None
    return FileResponse(image_path, filename=filename)


@router.get("/ui/normal-definitions/{file_name}")
async def fetch_normal_definition(file_name: str, request: Request) -> dict[str, Any]:
    safe_name = Path(file_name).name
    if not safe_name or safe_name != file_name:
        raise HTTPException(status_code=400, detail="Invalid definition identifier")

    store_dir = getattr(request.app.state, "normal_description_store_dir", None)
    candidates: list[Path] = []
    if store_dir:
        candidates.append(Path(store_dir) / safe_name)

    description_path = getattr(request.app.state, "normal_description_path", None)
    if description_path:
        description_path = Path(description_path)
        if description_path.name == safe_name:
            candidates.insert(0, description_path)

    seen: set[Path] = set()
    for candidate in candidates:
        candidate = candidate.resolve()
        if candidate in seen:
            continue
        seen.add(candidate)
        try:
            if candidate.exists() and candidate.is_file():
                description = candidate.read_text(encoding="utf-8")
                updated_at = datetime.fromtimestamp(candidate.stat().st_mtime, tz=timezone.utc).isoformat()
                return {"file": safe_name, "description": description, "updated_at": updated_at}
        except OSError:
            continue

    raise HTTPException(status_code=404, detail="Definition not found")


def _collect_recent_captures(
    root: Path,
    limit: int,
    *,
    states: Set[str] | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
    exclude_ids: Set[str] | None = None,
) -> List[CaptureSummary]:
    if limit <= 0:
        return []

    json_files = sorted(
        root.glob("**/*.json"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    matches: list[tuple[datetime, CaptureSummary]] = []

    for path in json_files:
        if len(matches) >= limit:
            break

        summary = load_capture_summary(path)
        if summary is None:
            continue

        if exclude_ids and summary.record_id in exclude_ids:
            continue

        if states is not None and summary.state not in states:
            continue

        captured_at_dt = summary.captured_at_dt
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


def _find_capture_json(root: Path, record_id: str) -> Optional[Path]:
    pattern = f"**/{record_id}.json"
    for path in root.glob(pattern):
        if path.is_file():
            return path
    return None




def _apply_normal_description(classifier: Any, description: str) -> None:
    if classifier is None:
        return
    visited: set[int] = set()

    def _walk(target: Any) -> None:
        if target is None:
            return
        identifier = id(target)
        if identifier in visited:
            return
        visited.add(identifier)
        if hasattr(target, "normal_description"):
            setattr(target, "normal_description", description)
        for attr in ("primary", "secondary"):
            child = getattr(target, attr, None)
            _walk(child)

    _walk(classifier)

__all__ = ["router"]
