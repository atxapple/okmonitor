from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse

from .schemas import (
    CaptureRequest,
    DeviceConfigResponse,
    InferenceResponse,
    TriggerConfigModel,
)
from .email_service import AbnormalCaptureNotifier
from .service import InferenceService
from .capture_index import RecentCaptureIndex
from .notification_settings import NotificationSettings
from ..ai import Classifier, SimpleThresholdModel
from ..datalake.storage import FileSystemDatalake
from ..web import register_ui


logger = logging.getLogger(__name__)


@dataclass
class TriggerConfig:
    enabled: bool = False
    interval_seconds: float | None = None


class TriggerHub:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._subscribers: dict[str, set[asyncio.Queue[str]]] = {}

    async def subscribe(self, device_id: str) -> asyncio.Queue[str]:
        queue: asyncio.Queue[str] = asyncio.Queue()
        async with self._lock:
            self._subscribers.setdefault(device_id, set()).add(queue)
        logger.debug(
            "TriggerHub subscribed device=%s total_subscribers=%d",
            device_id,
            len(self._subscribers),
        )
        return queue

    async def unsubscribe(self, device_id: str, queue: asyncio.Queue[str]) -> None:
        async with self._lock:
            queues = self._subscribers.get(device_id)
            if not queues:
                return
            queues.discard(queue)
            if not queues:
                self._subscribers.pop(device_id, None)
        logger.debug(
            "TriggerHub unsubscribed device=%s remaining=%d",
            device_id,
            len(self._subscribers),
        )

    async def publish(self, device_id: str, message: dict[str, str | int]) -> None:
        async with self._lock:
            queues = list(self._subscribers.get(device_id, ()))
        payload = json.dumps(message)
        logger.info(
            "Publishing trigger event device=%s subscribers=%d payload=%s",
            device_id,
            len(queues),
            payload,
        )
        for queue in queues:
            await queue.put(payload)


def create_app(
    root_dir: Path | None = None,
    classifier: Classifier | None = None,
    normal_description: str = "",
    normal_description_path: Path | None = None,
    device_id: str = "ui-device",
    abnormal_notifier: AbnormalCaptureNotifier | None = None,
    notification_settings: NotificationSettings | None = None,
    notification_config_path: Path | None = None,
    email_base_config: dict[str, str | None] | None = None,
    dedupe_enabled: bool = False,
    dedupe_threshold: int = 3,
    dedupe_keep_every: int = 5,
    streak_pruning_enabled: bool = False,
    streak_threshold: int = 0,
    streak_keep_every: int = 1,
) -> FastAPI:
    root = root_dir or Path("cloud_datalake")
    datalake = FileSystemDatalake(root=root)
    capture_index = RecentCaptureIndex(root=datalake.root)
    selected_classifier = classifier or SimpleThresholdModel()
    service = InferenceService(
        classifier=selected_classifier,
        datalake=datalake,
        capture_index=capture_index,
        notifier=abnormal_notifier,
        dedupe_enabled=dedupe_enabled,
        dedupe_threshold=dedupe_threshold,
        dedupe_keep_every=dedupe_keep_every,
        streak_pruning_enabled=streak_pruning_enabled,
        streak_threshold=streak_threshold,
        streak_keep_every=streak_keep_every,
    )

    app = FastAPI(title="OK Monitor API", version="0.1.0")

    trigger_config = TriggerConfig()
    trigger_hub = TriggerHub()

    description_store_dir = (
        normal_description_path.parent
        if normal_description_path is not None
        else Path("config/normal_descriptions")
    )
    try:
        description_store_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        logger.warning(
            "Failed to ensure normal description directory %s: %s",
            description_store_dir,
            exc,
        )
    current_description_file = (
        normal_description_path.name if normal_description_path is not None else None
    )

    settings = (notification_settings or NotificationSettings()).sanitized()

    app.state.classifier = selected_classifier
    app.state.service = service
    service.normal_description_file = current_description_file
    service.update_alert_cooldown(settings.email.abnormal_cooldown_minutes)
    service.update_dedupe_settings(dedupe_enabled, dedupe_threshold, dedupe_keep_every)
    service.update_streak_settings(
        streak_pruning_enabled, streak_threshold, streak_keep_every
    )
    app.state.abnormal_notifier = abnormal_notifier
    app.state.notification_settings = settings
    app.state.notification_config_path = notification_config_path
    app.state.email_base_config = email_base_config
    app.state.dedupe_enabled = dedupe_enabled
    app.state.dedupe_threshold = dedupe_threshold
    app.state.dedupe_keep_every = dedupe_keep_every
    app.state.streak_pruning_enabled = streak_pruning_enabled
    app.state.streak_threshold = streak_threshold
    app.state.streak_keep_every = streak_keep_every
    app.state.datalake = datalake
    app.state.datalake_root = datalake.root
    app.state.capture_index = capture_index
    app.state.normal_description = normal_description
    app.state.normal_description_path = normal_description_path
    app.state.normal_description_store_dir = description_store_dir
    app.state.normal_description_file = current_description_file
    app.state.trigger_config = trigger_config
    app.state.manual_trigger_counter = 0
    app.state.trigger_hub = trigger_hub
    app.state.device_id = device_id
    app.state.device_last_seen = None
    app.state.device_last_ip = None
    app.state.device_status_ttl = 30.0

    logger.info(
        "API server initialised device_id=%s classifier=%s datalake_root=%s streak_pruning=%s threshold=%d keep_every=%d",
        device_id,
        selected_classifier.__class__.__name__,
        datalake.root,
        streak_pruning_enabled,
        streak_threshold,
        streak_keep_every,
    )

    def _extract_client_ip(req: Request) -> str | None:
        header = req.headers.get("x-forwarded-for")
        if header:
            return header.split(",")[0].strip()
        if req.client:
            return req.client.host
        return None

    def _record_device_presence(req: Request) -> None:
        ip = _extract_client_ip(req)
        app.state.device_last_seen = datetime.now(timezone.utc)
        if ip:
            app.state.device_last_ip = ip

    @app.get("/health", response_model=dict[str, str])
    def healthcheck() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/v1/captures", response_model=InferenceResponse)
    def ingest_capture(request: CaptureRequest) -> InferenceResponse:
        logger.info(
            "Ingest capture device=%s trigger=%s payload_bytes=%d",
            request.device_id,
            request.trigger_label,
            len(request.image_base64 or ""),
        )
        try:
            result = service.process_capture(request.model_dump())
        except Exception as exc:  # pragma: no cover - surfaced via HTTP
            logger.exception(
                "Capture ingestion failed device=%s error=%s", request.device_id, exc
            )
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        logger.info(
            "Capture processed device=%s state=%s score=%.2f",
            request.device_id,
            result.get("state"),
            result.get("score", 0.0),
        )
        return InferenceResponse(**result)

    @app.get("/v1/device-config", response_model=DeviceConfigResponse)
    def fetch_device_config(
        request: Request, device_id_override: Optional[str] = None
    ) -> DeviceConfigResponse:
        _record_device_presence(request)
        config: TriggerConfig = app.state.trigger_config
        normal = getattr(app.state, "normal_description", "")
        target_id = device_id_override or app.state.device_id
        logger.debug(
            "Serving device config target=%s enabled=%s interval=%s",
            target_id,
            config.enabled,
            config.interval_seconds,
        )
        return DeviceConfigResponse(
            device_id=target_id,
            trigger=TriggerConfigModel(
                enabled=config.enabled,
                interval_seconds=config.interval_seconds,
            ),
            normal_description=normal,
            normal_description_file=getattr(app.state, "normal_description_file", None),
            manual_trigger_counter=app.state.manual_trigger_counter,
        )

    @app.post("/v1/manual-trigger", response_model=dict[str, int])
    async def manual_trigger(
        device_id_override: Optional[str] = None,
    ) -> dict[str, int]:
        target_id = device_id_override or app.state.device_id
        app.state.manual_trigger_counter += 1
        await trigger_hub.publish(
            target_id,
            {
                "event": "manual",
                "counter": app.state.manual_trigger_counter,
            },
        )
        logger.info(
            "Manual trigger issued device=%s counter=%d",
            target_id,
            app.state.manual_trigger_counter,
        )
        return {"manual_trigger_counter": app.state.manual_trigger_counter}

    @app.get("/v1/manual-trigger/stream")
    async def manual_trigger_stream(
        request: Request, device_id: str | None = None
    ) -> StreamingResponse:
        target_id = device_id or app.state.device_id
        _record_device_presence(request)
        queue = await trigger_hub.subscribe(target_id)
        logger.info("Trigger stream connected device=%s", target_id)

        async def event_generator() -> asyncio.AsyncIterator[str]:
            try:
                yield 'data: {"event": "connected"}\n\n'
                while True:
                    message = await queue.get()
                    yield f"data: {message}\n\n"
            finally:
                await trigger_hub.unsubscribe(target_id, queue)
                logger.info("Trigger stream disconnected device=%s", target_id)

        return StreamingResponse(event_generator(), media_type="text/event-stream")

    register_ui(app)

    return app


__all__ = ["create_app"]
