from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse

from .schemas import CaptureRequest, DeviceConfigResponse, InferenceResponse, TriggerConfigModel
from .service import InferenceService
from ..ai import Classifier, SimpleThresholdModel
from ..datalake.storage import FileSystemDatalake
from ..web import register_ui


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
        return queue

    async def unsubscribe(self, device_id: str, queue: asyncio.Queue[str]) -> None:
        async with self._lock:
            queues = self._subscribers.get(device_id)
            if not queues:
                return
            queues.discard(queue)
            if not queues:
                self._subscribers.pop(device_id, None)

    async def publish(self, device_id: str, message: dict[str, str | int]) -> None:
        async with self._lock:
            queues = list(self._subscribers.get(device_id, ()))
        payload = json.dumps(message)
        for queue in queues:
            await queue.put(payload)


def create_app(
    root_dir: Path | None = None,
    classifier: Classifier | None = None,
    normal_description: str = "",
    normal_description_path: Path | None = None,
    device_id: str = "ui-device",
) -> FastAPI:
    root = root_dir or Path("cloud_datalake")
    datalake = FileSystemDatalake(root=root)
    selected_classifier = classifier or SimpleThresholdModel()
    service = InferenceService(classifier=selected_classifier, datalake=datalake)

    app = FastAPI(title="OK Monitor API", version="0.1.0")

    trigger_config = TriggerConfig()
    trigger_hub = TriggerHub()

    app.state.classifier = selected_classifier
    app.state.service = service
    app.state.datalake = datalake
    app.state.datalake_root = datalake.root
    app.state.normal_description = normal_description
    app.state.normal_description_path = normal_description_path
    app.state.trigger_config = trigger_config
    app.state.manual_trigger_counter = 0
    app.state.trigger_hub = trigger_hub
    app.state.device_id = device_id

    @app.get("/health", response_model=dict[str, str])
    def healthcheck() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/v1/captures", response_model=InferenceResponse)
    def ingest_capture(request: CaptureRequest) -> InferenceResponse:
        try:
            result = service.process_capture(request.model_dump())
        except Exception as exc:  # pragma: no cover - surfaced via HTTP
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return InferenceResponse(**result)

    @app.get("/v1/device-config", response_model=DeviceConfigResponse)
    def fetch_device_config(device_id_override: Optional[str] = None) -> DeviceConfigResponse:
        config: TriggerConfig = app.state.trigger_config
        normal = getattr(app.state, "normal_description", "")
        return DeviceConfigResponse(
            device_id=device_id_override or app.state.device_id,
            trigger=TriggerConfigModel(
                enabled=config.enabled,
                interval_seconds=config.interval_seconds,
            ),
            normal_description=normal,
            manual_trigger_counter=app.state.manual_trigger_counter,
        )

    @app.post("/v1/manual-trigger", response_model=dict[str, int])
    async def manual_trigger(device_id_override: Optional[str] = None) -> dict[str, int]:
        target_id = device_id_override or app.state.device_id
        app.state.manual_trigger_counter += 1
        await trigger_hub.publish(
            target_id,
            {
                "event": "manual",
                "counter": app.state.manual_trigger_counter,
            },
        )
        return {"manual_trigger_counter": app.state.manual_trigger_counter}

    @app.get("/v1/manual-trigger/stream")
    async def manual_trigger_stream(device_id: str | None = None) -> StreamingResponse:
        target_id = device_id or app.state.device_id
        queue = await trigger_hub.subscribe(target_id)

        async def event_generator() -> asyncio.AsyncIterator[str]:
            try:
                yield "data: {\"event\": \"connected\"}\n\n"
                while True:
                    message = await queue.get()
                    yield f"data: {message}\n\n"
            finally:
                await trigger_hub.unsubscribe(target_id, queue)

        return StreamingResponse(event_generator(), media_type="text/event-stream")

    register_ui(app)

    return app


__all__ = ["create_app"]
