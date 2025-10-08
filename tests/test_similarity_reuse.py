from __future__ import annotations

import base64
import io
from datetime import datetime, timezone, timedelta

from PIL import Image

from cloud.ai.types import Classification
from cloud.api.service import InferenceService
from cloud.api.similarity_cache import SimilarityCache
from cloud.datalake.storage import FileSystemDatalake


def _encode_image(color: str) -> str:
    img = Image.new("RGB", (48, 48), color=color)
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return base64.b64encode(buf.getvalue()).decode("ascii")


class _CountingClassifier:
    def __init__(self) -> None:
        self.calls = 0

    def classify(self, image_bytes: bytes) -> Classification:
        self.calls += 1
        return Classification(state="normal", score=0.9, reason="steady")


def _build_payload(image_b64: str) -> dict[str, object]:
    return {
        "device_id": "device-a",
        "trigger_label": "scheduled",
        "metadata": {},
        "image_base64": image_b64,
    }


def test_similarity_reuse_skips_classifier_after_streak(tmp_path) -> None:
    classifier = _CountingClassifier()
    datalake = FileSystemDatalake(root=tmp_path / "datalake")
    cache = SimilarityCache(tmp_path / "cache.json")
    service = InferenceService(
        classifier=classifier,
        datalake=datalake,
        similarity_enabled=True,
        similarity_threshold=0,
        similarity_expiry_minutes=60.0,
        similarity_cache=cache,
        streak_threshold=2,
        streak_pruning_enabled=False,
    )

    image_b64 = _encode_image("red")

    first = service.process_capture(_build_payload(image_b64))
    second = service.process_capture(_build_payload(image_b64))
    third = service.process_capture(_build_payload(image_b64))

    assert classifier.calls == 2, (
        "Expected third capture to reuse cached classification"
    )
    assert first["state"] == "normal"
    assert second["state"] == "normal"
    assert third["state"] == "normal"
    assert third["record_id"]
    assert cache.get("device-a") is not None


def test_similarity_cache_expires_entries(tmp_path) -> None:
    cache = SimilarityCache(tmp_path / "cache.json")
    cache.update(
        device_id="device-a",
        record_id="abc",
        hash_hex="0" * 16,
        state="normal",
        score=0.5,
        reason=None,
        captured_at=datetime.now(timezone.utc) - timedelta(minutes=120),
    )
    cache.prune_expired(60)
    assert cache.get("device-a") is None
