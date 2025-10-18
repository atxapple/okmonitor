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
    classifier = _StubClassifier(
        Classification(state="abnormal", score=0.95, reason="anomaly")
    )
    datalake = FileSystemDatalake(root=tmp_path)
    notifier = _SpyNotifier()
    service = InferenceService(
        classifier=classifier, datalake=datalake, notifier=notifier
    )

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
    service = InferenceService(
        classifier=classifier, datalake=datalake, notifier=notifier
    )

    result = service.process_capture(_build_payload())

    assert result["state"] == "normal"
    assert not notifier.records


def test_device_timestamp_propagates_to_storage(tmp_path) -> None:
    classifier = _StubClassifier(Classification(state="normal", score=0.5, reason=None))
    datalake = FileSystemDatalake(root=tmp_path)
    service = InferenceService(classifier=classifier, datalake=datalake)

    device_time = "2025-10-20T15:30:45+02:00"
    payload = _build_payload()
    payload["captured_at"] = device_time

    result = service.process_capture(payload)
    record_id = result["record_id"]
    expected_dt = datetime.fromisoformat(device_time).astimezone(timezone.utc)
    expected_prefix = expected_dt.strftime("%Y%m%dT%H%M%S%fZ")
    assert record_id.startswith(f"device-123_{expected_prefix}")

    metadata_file = next(tmp_path.glob(f"**/{record_id}.json"))
    metadata = json.loads(metadata_file.read_text(encoding="utf-8"))
    assert metadata["captured_at"] == expected_dt.isoformat()
    assert "ingested_at" in metadata
    assert metadata["metadata"]["device_captured_at"] == expected_dt.isoformat()
    assert metadata["metadata"]["ingested_at"] == metadata["ingested_at"]
    assert metadata.get("image_filename") == f"{record_id}.jpeg"

    image_path = metadata_file.parent / metadata["image_filename"]
    assert image_path.exists()


def test_sendgrid_email_includes_image_and_definition(tmp_path) -> None:
    image_path = tmp_path / "capture.jpeg"
    image_path.write_bytes(b"fake-jpeg-bytes")
    metadata_path = tmp_path / "capture.json"
    metadata_path.write_text("{}", encoding="utf-8")
    description_dir = tmp_path / "normal_descriptions"
    description_dir.mkdir()
    description_file = description_dir / "normal.txt"
    description_file.write_text("Baseline operating procedures", encoding="utf-8")

    now = datetime.now(timezone.utc)
    record = CaptureRecord(
        record_id="abc123",
        image_path=image_path,
        metadata_path=metadata_path,
        captured_at=now,
        ingested_at=now,
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
        isinstance(att, Attachment)
        and getattr(att.content_id, "get", lambda: None)()
        == f"capture-{record.record_id}"
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


def test_alert_cooldown_blocks_until_reset(tmp_path) -> None:
    classifier = _StubClassifier(
        Classification(state="abnormal", score=0.95, reason="alert")
    )
    datalake = FileSystemDatalake(root=tmp_path)
    notifier = _SpyNotifier()
    service = InferenceService(
        classifier=classifier, datalake=datalake, notifier=notifier
    )
    service.update_alert_cooldown(30.0)

    service.process_capture(_build_payload())
    assert len(notifier.records) == 1

    service.process_capture(_build_payload())
    assert len(notifier.records) == 1

    classifier._classification = Classification(state="normal", score=0.2, reason=None)
    service.process_capture(_build_payload())
    assert len(notifier.records) == 1

    classifier._classification = Classification(
        state="abnormal", score=0.88, reason="again"
    )
    service.process_capture(_build_payload())
    assert len(notifier.records) == 2


def test_dedupe_skips_repeated_states(tmp_path) -> None:
    classifier = _StubClassifier(Classification(state="normal", score=1.0, reason=None))
    datalake = FileSystemDatalake(root=tmp_path)
    service = InferenceService(classifier=classifier, datalake=datalake)
    service.update_dedupe_settings(True, threshold=2, keep_every=3)

    ids = []
    for _ in range(6):
        result = service.process_capture(_build_payload())
        ids.append(result["record_id"])

    json_files = list(tmp_path.glob("**/*.json"))
    assert len(json_files) == 4
    assert ids[3] == ids[2]
    assert ids[4] == ids[2]
    assert ids[5] != ids[2]


def test_dedupe_resets_on_state_change(tmp_path) -> None:
    classifier = _StubClassifier(Classification(state="normal", score=1.0, reason=None))
    datalake = FileSystemDatalake(root=tmp_path)
    service = InferenceService(classifier=classifier, datalake=datalake)
    service.update_dedupe_settings(True, threshold=1, keep_every=3)

    first = service.process_capture(_build_payload())
    second = service.process_capture(_build_payload())
    third = service.process_capture(_build_payload())
    assert third["record_id"] == second["record_id"]

    classifier._classification = Classification(
        state="abnormal", score=0.9, reason="alert"
    )
    fourth = service.process_capture(_build_payload())
    assert fourth["record_id"] != third["record_id"]
    json_files = list(tmp_path.glob("**/*.json"))
    assert len(json_files) == 3


def test_streak_pruning_stores_metadata_only(tmp_path) -> None:
    classifier = _StubClassifier(Classification(state="normal", score=0.8, reason=None))
    datalake = FileSystemDatalake(root=tmp_path)
    service = InferenceService(
        classifier=classifier,
        datalake=datalake,
        streak_pruning_enabled=True,
        streak_threshold=2,
        streak_keep_every=3,
    )

    for _ in range(7):
        service.process_capture(_build_payload())

    json_files = sorted(tmp_path.glob("**/*.json"))
    assert len(json_files) == 7
    stored_flags = [
        json.loads(path.read_text(encoding="utf-8")).get("image_stored", True)
        for path in json_files
    ]
    assert stored_flags.count(True) == 3
    assert stored_flags.count(False) == 4
    image_files = list(tmp_path.glob("**/*.jpeg"))
    assert len(image_files) == 3


def test_streak_reset_on_state_change(tmp_path) -> None:
    classifier = _StubClassifier(Classification(state="normal", score=0.9, reason=None))
    datalake = FileSystemDatalake(root=tmp_path)
    service = InferenceService(
        classifier=classifier,
        datalake=datalake,
        streak_pruning_enabled=True,
        streak_threshold=1,
        streak_keep_every=4,
    )

    service.process_capture(_build_payload())
    service.process_capture(_build_payload())
    service.process_capture(_build_payload())

    classifier._classification = Classification(
        state="abnormal", score=0.5, reason="alert"
    )
    result = service.process_capture(_build_payload())

    metadata_file = next(tmp_path.glob(f"**/{result['record_id']}.json"))
    payload = json.loads(metadata_file.read_text(encoding="utf-8"))
    assert payload["classification"]["state"] == "abnormal"
    assert payload.get("image_stored") is True
    image_name = payload.get("image_filename")
    if image_name:
        image_file = metadata_file.parent / image_name
    else:
        image_file = metadata_file.with_suffix(".jpeg")
    assert image_file.exists()
