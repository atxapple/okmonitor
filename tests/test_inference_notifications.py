from __future__ import annotations

import json
import base64
from datetime import datetime, timezone

from sendgrid.helpers.mail import Attachment

from cloud.ai.types import Classification
from cloud.api.email_service import SendGridEmailConfig, SendGridEmailService
from cloud.api.service import InferenceService
from cloud.datalake.storage import CaptureRecord, FileSystemDatalake


class _StubClassifier:
    def __init__(self, classification: Classification) -> None:
        self._classification = classification
        self.last_image: bytes | None = None

    def classify(self, image_bytes: bytes) -> Classification:
        self.last_image = image_bytes
        return self._classification


class _SpyNotifier:
    def __init__(self) -> None:
        self.records = []

    def notify_abnormal(self, record) -> None:
        self.records.append(record)


class SendGridAPIClientStub:
    def __init__(self) -> None:
        self.sent_messages = []

    def send(self, message) -> None:  # pragma: no cover - stubbed behaviour
        self.sent_messages.append(message)


def _build_payload() -> dict[str, object]:
    return {
        "device_id": "device-123",
        "trigger_label": "scheduled",
        "metadata": {"extra": "value"},
        "image_base64": base64.b64encode(b"fake-image").decode("ascii"),
    }


def test_notifier_invoked_for_abnormal(tmp_path) -> None:
    classifier = _StubClassifier(Classification(state="abnormal", score=0.95, reason="anomaly"))
    datalake = FileSystemDatalake(root=tmp_path)
    notifier = _SpyNotifier()
    service = InferenceService(classifier=classifier, datalake=datalake, notifier=notifier)

    result = service.process_capture(_build_payload())

    assert result["state"] == "abnormal"
    assert len(notifier.records) == 1
    record = notifier.records[0]
    assert record.metadata["device_id"] == "device-123"
    assert record.classification["reason"] == "anomaly"
    assert record.image_path.exists()


def test_notifier_skipped_for_normal(tmp_path) -> None:
    classifier = _StubClassifier(Classification(state="normal", score=0.4, reason=None))
    datalake = FileSystemDatalake(root=tmp_path)
    notifier = _SpyNotifier()
    service = InferenceService(classifier=classifier, datalake=datalake, notifier=notifier)

    result = service.process_capture(_build_payload())

    assert result["state"] == "normal"
    assert not notifier.records


def test_sendgrid_email_includes_image_and_definition(tmp_path) -> None:
    image_path = tmp_path / "capture.jpeg"
    image_path.write_bytes(b"fake-jpeg-bytes")
    metadata_path = tmp_path / "capture.json"
    metadata_path.write_text("{}", encoding="utf-8")
    description_dir = tmp_path / "normal_descriptions"
    description_dir.mkdir()
    description_file = description_dir / "normal.txt"
    description_file.write_text("Baseline operating procedures", encoding="utf-8")

    record = CaptureRecord(
        record_id="abc123",
        image_path=image_path,
        metadata_path=metadata_path,
        captured_at=datetime.now(timezone.utc),
        metadata={"device_id": "device-123"},
        classification={"state": "abnormal", "score": 0.98, "reason": "anomaly"},
        normal_description_file=description_file.name,
    )

    config = SendGridEmailConfig(
        api_key="dummy",
        sender="alerts@example.com",
        recipients=["ops@example.com"],
        ui_base_url="http://localhost:8000",
    )
    service = SendGridEmailService(
        config=config,
        client=SendGridAPIClientStub(),
        description_root=description_dir,
    )

    normal_description = service._load_normal_description(record)  # noqa: SLF001 - exercising helper
    assert normal_description == "Baseline operating procedures"

    classification = record.classification
    sent_at = "2025-09-28T12:34:56Z"
    html_preview = service._render_html(  # noqa: SLF001 - exercising helper
        service._render_subject(record),
        record.metadata,
        classification.get("state"),
        classification.get("score"),
        classification.get("reason"),
        record,
        sent_at,
        normal_description,
        "preview-cid",
        "http://localhost:8000/ui",
    )

    assert "Baseline operating procedures" in html_preview
    assert "cid:preview-cid" in html_preview
    assert "http://localhost:8000/ui" in html_preview

    message = service._build_message(record)  # noqa: SLF001 - exercising private helper

    attachments = message.attachments or []
    assert any(
        isinstance(att, Attachment) and getattr(att.content_id, "get", lambda: None)() == f"capture-{record.record_id}"
        for att in attachments
    )
    plain_preview = service._render_plain(  # noqa: SLF001 - exercising helper
        service._render_subject(record),
        record.metadata,
        classification.get("state"),
        classification.get("score"),
        classification.get("reason"),
        record,
        sent_at,
        normal_description,
        "http://localhost:8000/ui",
    )
    plain_payload = json.loads(plain_preview)
    assert plain_payload.get("capture_url") == "http://localhost:8000/ui"
