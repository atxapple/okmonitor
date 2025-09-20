from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from fastapi import FastAPI, HTTPException

from .schemas import CaptureRequest, InferenceResponse
from .service import InferenceService
from ..ai.simple import SimpleThresholdModel
from ..datalake.storage import FileSystemDatalake


def create_app(root_dir: Path | None = None) -> FastAPI:
    root = root_dir or Path("cloud_datalake")
    classifier = SimpleThresholdModel()
    datalake = FileSystemDatalake(root=root)
    service = InferenceService(classifier=classifier, datalake=datalake)

    app = FastAPI(title="OK Monitor API", version="0.1.0")

    @app.get("/health", response_model=Dict[str, str])
    def healthcheck() -> Dict[str, str]:
        return {"status": "ok"}

    @app.post("/v1/captures", response_model=InferenceResponse)
    def ingest_capture(request: CaptureRequest) -> InferenceResponse:
        try:
            result = service.process_capture(request.model_dump())
        except Exception as exc:  # pragma: no cover - surfaced via HTTP
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return InferenceResponse(**result)

    return app


__all__ = ["create_app"]