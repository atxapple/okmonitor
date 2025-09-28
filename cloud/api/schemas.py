from __future__ import annotations

from typing import Any, Dict

from pydantic import BaseModel, Field


class CaptureRequest(BaseModel):
    device_id: str = Field(..., description="Unique identifier for the device")
    trigger_label: str = Field(..., description="Label provided by trigger source")
    image_base64: str = Field(..., description="Base64 encoded image")
    metadata: Dict[str, Any] = Field(default_factory=dict)


class InferenceResponse(BaseModel):
    record_id: str
    state: str
    score: float
    reason: str | None = None


class TriggerConfigModel(BaseModel):
    enabled: bool
    interval_seconds: float | None = None


class DeviceConfigResponse(BaseModel):
    device_id: str
    trigger: TriggerConfigModel
    normal_description: str
    normal_description_file: str | None = None
    manual_trigger_counter: int = 0


__all__ = [
    "CaptureRequest",
    "InferenceResponse",
    "TriggerConfigModel",
    "DeviceConfigResponse",
]
