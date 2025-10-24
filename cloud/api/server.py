from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse, FileResponse

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
from .persistent_config import load_server_config
from .timing_debug import init_timing_stats, get_timing_stats, CaptureTimings
from .datalake_pruner import prune_datalake, PruneStats
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
    timing_debug_enabled: bool = False,
    timing_debug_max_captures: int = 100,
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
    # Initialize timing debug if enabled
    timing_stats = init_timing_stats(
        enabled=timing_debug_enabled,
        max_captures=timing_debug_max_captures
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

    # Load persistent server configuration
    server_config_path = Path("/mnt/data/config/server_config.json")
    persistent_config = load_server_config(server_config_path)

    # Initialize trigger config from persistent storage
    trigger_config = TriggerConfig(
        enabled=persistent_config.trigger.enabled,
        interval_seconds=persistent_config.trigger.interval_seconds,
    )
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
    app.state.server_config_path = server_config_path
    app.state.manual_trigger_counter = 0
    app.state.trigger_hub = trigger_hub
    app.state.capture_hub = capture_hub
    app.state.device_id = device_id
    app.state.device_last_seen = None
    app.state.device_last_ip = None
    app.state.device_status_ttl = 30.0
    app.state.timing_debug_enabled = timing_debug_enabled
    app.state.timing_stats = timing_stats
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
        "API server initialised device_id=%s classifier=%s datalake_root=%s streak_pruning=%s threshold=%d keep_every=%d similarity=%s hash_threshold=%d expiry=%.2f timing_debug=%s",
        device_id,
        selected_classifier.__class__.__name__,
        datalake.root,
        streak_pruning_enabled,
        streak_threshold,
        streak_keep_every,
        similarity_enabled,
        similarity_threshold,
        similarity_expiry_minutes,
        timing_debug_enabled,
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
        import time

        # Timing debug: Record request received timestamp
        timing = None
        if app.state.timing_debug_enabled:
            timing = CaptureTimings(
                record_id="",  # Will be filled in later
                device_id=request.device_id,
                t3_server_request_received=time.time(),
            )
            # Copy device timestamps if provided
            if request.debug_timestamps:
                timing.t0_device_capture = request.debug_timestamps.get("t0_device_capture")
                timing.t1_device_thumbnail = request.debug_timestamps.get("t1_device_thumbnail")
                timing.t2_device_request_sent = request.debug_timestamps.get("t2_device_request_sent")

        logger.info(
            "Ingest capture device=%s trigger=%s payload_bytes=%d",
            request.device_id,
            request.trigger_label,
            len(request.image_base64 or ""),
        )
        try:
            result = service.process_capture(request.model_dump(), timing=timing)
        except Exception as exc:  # pragma: no cover - surfaced via HTTP
            logger.exception(
                "Capture ingestion failed device=%s error=%s", request.device_id, exc
            )
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        # Timing debug: Record broadcast start
        if timing:
            timing.t8_server_broadcast_complete = time.time()

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

        # Timing debug: Record response sent and store timing data
        if timing and result.get("record_id"):
            timing.record_id = result.get("record_id", "")
            timing.state = result.get("state")
            timing.t9_server_response_sent = time.time()
            if app.state.timing_stats:
                app.state.timing_stats.add_timing(timing)

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

    @app.websocket("/ws/captures")
    async def websocket_captures(websocket: WebSocket, device_id: str | None = None) -> None:
        """WebSocket endpoint for real-time capture notifications."""
        await websocket.accept()

        if device_id and device_id.lower() == "all":
            target_key = "__all__"
        else:
            target_key = device_id or app.state.device_id

        queue = await capture_hub.subscribe(target_key)
        logger.info("WebSocket connected target=%s", target_key)

        try:
            await websocket.send_json({"event": "connected", "target": target_key})

            while True:
                message = await queue.get()
                if message == _QUEUE_SHUTDOWN:
                    break

                # Send message to WebSocket client
                try:
                    data = json.loads(message) if isinstance(message, str) else message
                    await websocket.send_json(data)
                except WebSocketDisconnect:
                    break
                except Exception as exc:
                    logger.warning("Failed to send WebSocket message: %s", exc)
                    break

        except WebSocketDisconnect:
            logger.info("WebSocket disconnected target=%s", target_key)
        except Exception as exc:
            logger.exception("WebSocket error target=%s: %s", target_key, exc)
        finally:
            await capture_hub.unsubscribe(target_key, queue)
            logger.info("WebSocket cleanup complete target=%s", target_key)

    @app.get("/v1/captures/{record_id}/thumbnail")
    async def get_thumbnail(record_id: str) -> FileResponse:
        """Serve thumbnail image for a capture record."""
        # Parse record_id to find the file
        # Format: {device}_{timestamp}_{hash}
        # Files stored in: datalake/YYYY/MM/DD/{record_id}_thumb.jpeg

        # Try to find the thumbnail file
        # We need to search through the datalake structure
        root = Path(app.state.datalake_root)

        # Quick search through recent days (optimization)
        from datetime import timedelta
        today = datetime.now(timezone.utc)

        for days_ago in range(30):  # Search last 30 days
            check_date = today - timedelta(days=days_ago)
            date_path = root / check_date.strftime("%Y/%m/%d")
            thumbnail_path = date_path / f"{record_id}_thumb.jpeg"

            if thumbnail_path.exists():
                return FileResponse(
                    thumbnail_path,
                    media_type="image/jpeg",
                    headers={"Cache-Control": "public, max-age=86400"}  # Cache for 1 day
                )

        raise HTTPException(status_code=404, detail=f"Thumbnail not found for record {record_id}")

    @app.post("/v1/admin/prune-datalake")
    async def prune_datalake_endpoint(
        dry_run: bool = False,
        retention_days: int | None = None,
    ) -> dict[str, int | str]:
        """Manually trigger datalake pruning.

        Args:
            dry_run: If True, don't actually delete files, just report what would be deleted
            retention_days: Override the configured retention period
        """
        # Use configured retention if not provided
        if retention_days is None:
            # Get from app state or default
            retention_days = getattr(app.state, "pruning_retention_days", 3)

        logger.info(f"Manual pruning triggered: retention={retention_days} days, dry_run={dry_run}")

        try:
            stats = prune_datalake(datalake.root, retention_days, dry_run=dry_run)
            return {
                "status": "dry_run" if dry_run else "completed",
                "files_scanned": stats.files_scanned,
                "images_deleted": stats.images_deleted,
                "images_preserved": stats.images_preserved,
                "abnormal_preserved": stats.abnormal_preserved,
                "bytes_freed": stats.bytes_freed,
                "errors": stats.errors,
            }
        except Exception as exc:
            logger.error(f"Manual pruning failed: {exc}")
            raise HTTPException(status_code=500, detail=str(exc))

    @app.get("/v1/admin/prune-datalake/stats")
    async def prune_datalake_stats(retention_days: int | None = None) -> dict[str, int | str]:
        """Preview what would be deleted by pruning (dry-run mode)."""
        if retention_days is None:
            retention_days = getattr(app.state, "pruning_retention_days", 3)

        try:
            stats = prune_datalake(datalake.root, retention_days, dry_run=True)
            return {
                "status": "preview",
                "retention_days": retention_days,
                "files_scanned": stats.files_scanned,
                "images_would_delete": stats.images_deleted,
                "images_would_preserve": stats.images_preserved,
                "abnormal_preserved": stats.abnormal_preserved,
                "bytes_would_free": stats.bytes_freed,
                "mb_would_free": round(stats.bytes_freed / 1024 / 1024, 2),
            }
        except Exception as exc:
            logger.error(f"Pruning stats failed: {exc}")
            raise HTTPException(status_code=500, detail=str(exc))

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
