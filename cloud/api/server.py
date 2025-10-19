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
from .similarity_cache import SimilarityCache
from ..ai import Classifier, SimpleThresholdModel
from ..datalake.storage import FileSystemDatalake
from ..web import register_ui
from ..web.preferences import UIPreferences, load_preferences


logger = logging.getLogger(__name__)


@dataclass
class TriggerConfig:
    enabled: bool = False
    interval_seconds: float | None = None


_QUEUE_SHUTDOWN = "__shutdown__"


class TriggerHub:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._subscribers: dict[str, set[asyncio.Queue[str]]] = {}
        self._closing = False

    async def subscribe(self, device_id: str) -> asyncio.Queue[str]:
        queue: asyncio.Queue[str] = asyncio.Queue()
        async with self._lock:
            if self._closing:
                queue.put_nowait(_QUEUE_SHUTDOWN)
                return queue
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
            if self._closing:
                return
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

    async def close(self) -> None:
        async with self._lock:
            self._closing = True
            queues = [q for qs in self._subscribers.values() for q in qs]
            self._subscribers.clear()
        logger.info("TriggerHub closing queues=%d", len(queues))
        for queue in queues:
            queue.put_nowait(_QUEUE_SHUTDOWN)


class CaptureHub:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._subscribers: dict[str, set[asyncio.Queue[str]]] = {}
        self._closing = False

    async def subscribe(self, key: str) -> asyncio.Queue[str]:
        queue: asyncio.Queue[str] = asyncio.Queue()
        async with self._lock:
            if self._closing:
                queue.put_nowait(_QUEUE_SHUTDOWN)
                return queue
            self._subscribers.setdefault(key, set()).add(queue)
        logger.debug(
            "CaptureHub subscribed key=%s total=%d",
            key,
            len(self._subscribers),
        )
        return queue

    async def unsubscribe(self, key: str, queue: asyncio.Queue[str]) -> None:
        async with self._lock:
            queues = self._subscribers.get(key)
            if not queues:
                return
            queues.discard(queue)
            if not queues:
                self._subscribers.pop(key, None)
        logger.debug(
            "CaptureHub unsubscribed key=%s remaining=%d",
            key,
            len(self._subscribers),
        )

    async def publish(self, device_id: str, message: dict[str, object]) -> None:
        async with self._lock:
            if self._closing:
                return
            device_queues = list(self._subscribers.get(device_id, ()))
            broadcast_queues = list(self._subscribers.get("__all__", ()))
        payload = json.dumps(message)
        total = len(device_queues) + len(broadcast_queues)
        logger.debug(
            "Publishing capture event device=%s subscribers=%d payload=%s",
            device_id,
            total,
            payload,
        )
        for queue in device_queues + broadcast_queues:
            await queue.put(payload)

    async def close(self) -> None:
        async with self._lock:
            self._closing = True
            queues = [q for qs in self._subscribers.values() for q in qs]
            self._subscribers.clear()
        logger.info("CaptureHub closing queues=%d", len(queues))
        for queue in queues:
            queue.put_nowait(_QUEUE_SHUTDOWN)


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
    similarity_enabled: bool = False,
    similarity_threshold: int = 6,
    similarity_expiry_minutes: float = 60.0,
    similarity_cache_path: str | None = None,
    streak_pruning_enabled: bool = False,
    streak_threshold: int = 0,
    streak_keep_every: int = 1,
) -> FastAPI:
    root = root_dir or Path("/mnt/data/datalake")
    datalake = FileSystemDatalake(root=root)
    capture_index = RecentCaptureIndex(root=datalake.root)
    selected_classifier = classifier or SimpleThresholdModel()
    similarity_cache = (
        SimilarityCache(Path(similarity_cache_path))
        if similarity_enabled and similarity_cache_path
        else None
    )
    service = InferenceService(
        classifier=selected_classifier,
        datalake=datalake,
        capture_index=capture_index,
        notifier=abnormal_notifier,
        dedupe_enabled=dedupe_enabled,
        dedupe_threshold=dedupe_threshold,
        dedupe_keep_every=dedupe_keep_every,
        similarity_enabled=similarity_enabled,
        similarity_threshold=similarity_threshold,
        similarity_expiry_minutes=similarity_expiry_minutes,
        similarity_cache=similarity_cache,
        streak_pruning_enabled=streak_pruning_enabled,
        streak_threshold=streak_threshold,
        streak_keep_every=streak_keep_every,
    )

    app = FastAPI(title="OK Monitor API", version="0.1.0")

    trigger_config = TriggerConfig()
    trigger_hub = TriggerHub()
    capture_hub = CaptureHub()

    description_store_dir = (
        normal_description_path.parent
        if normal_description_path is not None
        else Path("/mnt/data/config/normal_descriptions")
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
    app.state.notification_config_path = notification_config_path or Path(
        "/mnt/data/config/notifications.json"
    )
    app.state.email_base_config = email_base_config
    app.state.dedupe_enabled = dedupe_enabled
    app.state.dedupe_threshold = dedupe_threshold
    app.state.dedupe_keep_every = dedupe_keep_every
    app.state.similarity_enabled = similarity_enabled
    app.state.similarity_threshold = similarity_threshold
    app.state.similarity_expiry_minutes = similarity_expiry_minutes
    app.state.similarity_cache_path = (
        Path(similarity_cache_path)
        if similarity_cache_path
        else Path("/mnt/data/config/similarity_cache.json")
    )
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
    app.state.capture_hub = capture_hub
    app.state.device_id = device_id
    app.state.device_last_seen = None
    app.state.device_last_ip = None
    app.state.device_status_ttl = 30.0
    preferences_path = Path("/mnt/data/config/ui_preferences.json")
    app.state.ui_preferences_path = preferences_path
    try:
        app.state.ui_preferences = load_preferences(preferences_path)
    except Exception:
        logger.warning(
            "Failed to load UI preferences from %s; using defaults", preferences_path
        )
        app.state.ui_preferences = UIPreferences()

    logger.info(
        "API server initialised device_id=%s classifier=%s datalake_root=%s streak_pruning=%s threshold=%d keep_every=%d similarity=%s hash_threshold=%d expiry=%.2f",
        device_id,
        selected_classifier.__class__.__name__,
        datalake.root,
        streak_pruning_enabled,
        streak_threshold,
        streak_keep_every,
        similarity_enabled,
        similarity_threshold,
        similarity_expiry_minutes,
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
    async def ingest_capture(request: CaptureRequest) -> InferenceResponse:
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
        if result.get("created") and result.get("record_id"):
            event_payload = {
                "event": "capture",
                "device_id": request.device_id,
                "record_id": result.get("record_id"),
                "state": result.get("state"),
                "captured_at": result.get("captured_at"),
            }
            try:
                await capture_hub.publish(request.device_id, event_payload)
            except Exception:
                logger.exception(
                    "Failed to publish capture event device=%s record_id=%s",
                    request.device_id,
                    result.get("record_id"),
                )
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
            shutdown_event: asyncio.Event | None = getattr(
                app.state, "shutdown_event", None
            )
            try:
                yield 'data: {"event": "connected"}\n\n'
                while True:
                    try:
                        message = (
                            await asyncio.wait_for(queue.get(), timeout=0.1)
                            if shutdown_event is not None
                            else await queue.get()
                        )
                    except asyncio.TimeoutError:
                        if shutdown_event is not None and shutdown_event.is_set():
                            logger.debug(
                                "Trigger stream shutdown detected device=%s",
                                target_id,
                            )
                            break
                        continue
                    except asyncio.CancelledError:
                        # Expected during graceful shutdown timeout
                        logger.debug("Trigger stream cancelled during shutdown device=%s", target_id)
                        break
                    if message == _QUEUE_SHUTDOWN:
                        break
                    yield f"data: {message}\n\n"
            except asyncio.CancelledError:
                # Expected when uvicorn forcefully cancels tasks on shutdown timeout
                logger.debug("Trigger stream task cancelled device=%s", target_id)
            finally:
                await trigger_hub.unsubscribe(target_id, queue)
                logger.info("Trigger stream disconnected device=%s", target_id)

        return StreamingResponse(event_generator(), media_type="text/event-stream")

    @app.get("/v1/capture-events/stream")
    async def capture_events_stream(
        request: Request, device_id: str | None = None
    ) -> StreamingResponse:
        if device_id and device_id.lower() == "all":
            target_key = "__all__"
        else:
            target_key = device_id or app.state.device_id
        queue = await capture_hub.subscribe(target_key)
        logger.info("Capture stream connected target=%s", target_key)

        async def event_generator() -> asyncio.AsyncIterator[str]:
            shutdown_event: asyncio.Event | None = getattr(
                app.state, "shutdown_event", None
            )
            try:
                yield 'data: {"event": "connected"}\n\n'
                while True:
                    try:
                        message = (
                            await asyncio.wait_for(queue.get(), timeout=0.1)
                            if shutdown_event is not None
                            else await queue.get()
                        )
                    except asyncio.TimeoutError:
                        if shutdown_event is not None and shutdown_event.is_set():
                            logger.debug(
                                "Capture stream shutdown detected target=%s",
                                target_key,
                            )
                            break
                        continue
                    except asyncio.CancelledError:
                        # Expected during graceful shutdown timeout
                        logger.debug("Capture stream cancelled during shutdown target=%s", target_key)
                        break
                    if message == _QUEUE_SHUTDOWN:
                        break
                    yield f"data: {message}\n\n"
            except asyncio.CancelledError:
                # Expected when uvicorn forcefully cancels tasks on shutdown timeout
                logger.debug("Capture stream task cancelled target=%s", target_key)
            finally:
                await capture_hub.unsubscribe(target_key, queue)
                logger.info("Capture stream disconnected target=%s", target_key)

        return StreamingResponse(event_generator(), media_type="text/event-stream")

    @app.on_event("startup")
    async def _init_shutdown_event() -> None:
        if getattr(app.state, "shutdown_event", None) is None:
            app.state.shutdown_event = asyncio.Event()

    @app.on_event("shutdown")
    async def _shutdown_streams() -> None:
        shutdown_event: asyncio.Event | None = getattr(
            app.state, "shutdown_event", None
        )
        if shutdown_event is not None:
            shutdown_event.set()
        await trigger_hub.close()
        await capture_hub.close()

    register_ui(app)

    return app


__all__ = ["create_app"]
