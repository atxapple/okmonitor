from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException

from .schemas import CaptureRequest, DeviceConfigResponse, InferenceResponse, TriggerConfigModel
from .service import InferenceService
from ..ai import Classifier, SimpleThresholdModel
from ..datalake.storage import FileSystemDatalake
from ..web import register_ui


@dataclass
class TriggerConfig:
    enabled: bool = False
    interval_seconds: float | None = None


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

    app.state.classifier = selected_classifier
    app.state.service = service
    app.state.datalake = datalake
    app.state.datalake_root = datalake.root
    app.state.normal_description = normal_description
    app.state.normal_description_path = normal_description_path
    app.state.trigger_config = trigger_config
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
        response = DeviceConfigResponse(
            device_id=device_id_override or app.state.device_id,
            trigger=TriggerConfigModel(
                enabled=config.enabled,
                interval_seconds=config.interval_seconds,
            ),
            normal_description=normal,
        )
        return response

    register_ui(app)

    return app


__all__ = ["create_app"]
