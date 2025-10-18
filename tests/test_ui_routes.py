import json
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from cloud.ai.consensus import ConsensusClassifier
from cloud.ai.types import Classification, Classifier
from cloud.api.notification_settings import NotificationSettings
from cloud.api.server import create_app


class _DummyClassifier(Classifier):
    def __init__(self) -> None:
        self.normal_description = "Initial"

    def classify(self, image_bytes: bytes) -> Classification:
        return Classification(state="normal", score=1.0, reason=None)


class UiRoutesTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_state_and_description_update(self) -> None:
        normal_path = self.tmp_path / "normal.txt"
        app = create_app(
            root_dir=self.tmp_path / "datalake",
            normal_description="Initial normal",
            normal_description_path=normal_path,
        )

        with TestClient(app) as client:
            response = client.get("/ui/state")
            data = response.json()
            self.assertEqual(data["normal_description"], "Initial normal")
            self.assertEqual(data["normal_description_file"], "normal.txt")
            self.assertEqual(data["device_id"], "ui-device")
            self.assertEqual(
                data["trigger"], {"enabled": False, "interval_seconds": None}
            )
            self.assertEqual(data["manual_trigger_counter"], 0)
            notifications = data.get("notifications")
            self.assertIsNotNone(notifications)
            self.assertEqual(
                notifications["email"],
                {"enabled": False, "recipients": [], "cooldown_minutes": 10.0},
            )
            dedupe = data.get("dedupe")
            self.assertEqual(
                dedupe, {"enabled": False, "threshold": 3, "keep_every": 5}
            )
            status = data.get("device_status")
            self.assertIsNotNone(status)
            self.assertFalse(status["connected"])
            self.assertIsNone(status["last_seen"])
            self.assertIsNone(status["ip"])

            update = client.post(
                "/ui/normal-description", json={"description": "Updated"}
            )
            self.assertEqual(update.status_code, 200)
            payload = update.json()
            self.assertEqual(payload["normal_description"], "Updated")
            file_name = payload["normal_description_file"]
            self.assertTrue(file_name.startswith("normal_"))
            version_path = normal_path.parent / file_name
            self.assertTrue(version_path.exists())
            self.assertEqual(version_path.read_text(encoding="utf-8"), "Updated")

            definition = client.get(f"/ui/normal-definitions/{file_name}")
            self.assertEqual(definition.status_code, 200)
            definition_payload = definition.json()
            self.assertEqual(definition_payload["file"], file_name)
            self.assertEqual(definition_payload["description"], "Updated")

            state_after = client.get("/ui/state").json()
            self.assertEqual(state_after["normal_description_file"], file_name)

    def test_description_update_propagates_to_nested_classifiers(self) -> None:
        normal_path = self.tmp_path / "normal_nested.txt"
        consensus = ConsensusClassifier(
            primary=_DummyClassifier(), secondary=_DummyClassifier()
        )
        app = create_app(
            root_dir=self.tmp_path / "datalake_nested",
            normal_description="Initial",
            normal_description_path=normal_path,
            classifier=consensus,
        )

        with TestClient(app) as client:
            response = client.post(
                "/ui/normal-description", json={"description": "New guidance"}
            )
            self.assertEqual(response.status_code, 200)
            payload = response.json()
            self.assertIn("normal_description_file", payload)
            version_path = normal_path.parent / payload["normal_description_file"]
            self.assertTrue(version_path.exists())
        self.assertEqual(consensus.primary.normal_description, "New guidance")
        self.assertEqual(consensus.secondary.normal_description, "New guidance")

    def test_device_status_updates_on_config_fetch(self) -> None:
        normal_path = self.tmp_path / "normal_status.txt"
        app = create_app(
            root_dir=self.tmp_path / "datalake_status",
            normal_description="Initial",
            normal_description_path=normal_path,
        )

        with TestClient(app) as client:
            response = client.get("/v1/device-config")
            self.assertEqual(response.status_code, 200)
            state = client.get("/ui/state").json()
            status = state["device_status"]
            self.assertTrue(status["connected"])
            self.assertIsNotNone(status["last_seen"])
            self.assertTrue(status["ip"])

    def test_capture_listing_and_trigger_controls(self) -> None:
        datalake_dir = self.tmp_path / "datalake"
        app = create_app(
            root_dir=datalake_dir,
            normal_description="",
            normal_description_path=self.tmp_path / "normal.txt",
        )

        sample_image = Path("samples/test.jpg")
        self.assertTrue(sample_image.exists(), "Expected sample image to exist")

        datalake = app.state.datalake
        record = datalake.store_capture(
            image_bytes=sample_image.read_bytes(),
            metadata={"trigger_label": "ui-test"},
            classification={
                "state": "abnormal",
                "score": 0.9,
                "reason": "Integration test",
            },
            device_id="ui-device",
        )

        with TestClient(app) as client:
            captures = client.get("/ui/captures")
            self.assertEqual(captures.status_code, 200)
            payload = captures.json()
            self.assertTrue(payload, "Expected at least one capture")
            first = payload[0]
            self.assertEqual(first["record_id"], record.record_id)
            self.assertEqual(first["reason"], "Integration test")
            self.assertEqual(first["captured_at"], record.captured_at.isoformat())
            self.assertIsNotNone(first.get("ingested_at"))
            self.assertIn("normal_description_file", first)
            self.assertIsNone(first["normal_description_file"])
            self.assertTrue(first.get("image_url"))
            self.assertTrue(first.get("download_url"))
            self.assertTrue(first["download_url"].endswith("?download=1"))

            image_resp = client.get(f"/ui/captures/{record.record_id}/image")
            self.assertEqual(image_resp.status_code, 200)
            self.assertTrue(image_resp.headers["content-type"].startswith("image/"))

            download_resp = client.get(
                f"/ui/captures/{record.record_id}/image", params={"download": "1"}
            )
            self.assertEqual(download_resp.status_code, 200)
            self.assertIn(
                "attachment",
                download_resp.headers.get("content-disposition", "").lower(),
            )

            datalake.store_capture(
                image_bytes=None,
                metadata={"trigger_label": "ui-test"},
                classification={
                    "state": "normal",
                    "score": 0.8,
                    "reason": "Deduplicated streak",
                },
                store_image=False,
                device_id="ui-device",
            )

            subsequent = client.get("/ui/captures")
            self.assertEqual(subsequent.status_code, 200)
            subsequent_payload = subsequent.json()
            self.assertEqual(len(subsequent_payload), 1)
            self.assertEqual(subsequent_payload[0]["record_id"], record.record_id)

            enable = client.post(
                "/ui/trigger", json={"enabled": True, "interval_seconds": 10}
            )
            self.assertEqual(enable.status_code, 200)
            self.assertTrue(enable.json()["trigger"]["enabled"])

            disable = client.post(
                "/ui/trigger", json={"enabled": False, "interval_seconds": None}
            )
            self.assertEqual(disable.status_code, 200)
            self.assertFalse(disable.json()["trigger"]["enabled"])

            manual = client.post("/v1/manual-trigger")
            self.assertEqual(manual.status_code, 200)

            config_resp = client.get("/v1/device-config")
            self.assertEqual(config_resp.status_code, 200)
            config_payload = config_resp.json()
            self.assertEqual(config_payload["device_id"], "ui-device")
            self.assertEqual(
                config_payload["trigger"], {"enabled": False, "interval_seconds": None}
            )
            self.assertGreaterEqual(config_payload["manual_trigger_counter"], 1)

    def test_normal_definition_lookup_validation(self) -> None:
        app = create_app(
            root_dir=self.tmp_path / "datalake_lookup",
            normal_description="",
            normal_description_path=self.tmp_path / "lookup_seed.txt",
        )

        with TestClient(app) as client:
            missing = client.get("/ui/normal-definitions/missing.txt")
            self.assertEqual(missing.status_code, 404)

    def test_notification_updates_via_ui(self) -> None:
        config_path = self.tmp_path / "notifications.json"
        app = create_app(
            root_dir=self.tmp_path / "datalake_notifications",
            normal_description="",
            normal_description_path=self.tmp_path / "normal_notify.txt",
            notification_settings=NotificationSettings(),
            notification_config_path=config_path,
            email_base_config={
                "api_key": "test-key",
                "sender": "alerts@example.com",
                "environment_label": None,
            },
        )

        with TestClient(app) as client:
            state = client.get("/ui/state").json()
            self.assertFalse(state["notifications"]["email"]["enabled"])

            bad = client.post(
                "/ui/notifications",
                json={"email_enabled": True, "email_recipients": []},
            )
            self.assertEqual(bad.status_code, 400)

            good = client.post(
                "/ui/notifications",
                json={
                    "email_enabled": True,
                    "email_recipients": ["ops@example.com", "ops@example.com"],
                    "email_cooldown_minutes": 5,
                },
            )
            self.assertEqual(good.status_code, 200)
            payload = good.json()
            self.assertTrue(payload["notifications"]["email"]["enabled"])
            self.assertEqual(
                payload["notifications"]["email"]["recipients"], ["ops@example.com"]
            )

            saved = json.loads(config_path.read_text())
            self.assertEqual(saved["email"]["recipients"], ["ops@example.com"])
            self.assertEqual(saved["email"].get("abnormal_cooldown_minutes"), 5.0)

            state_after = client.get("/ui/state").json()
            self.assertTrue(state_after["notifications"]["email"]["enabled"])
            self.assertEqual(
                state_after["notifications"]["email"]["recipients"], ["ops@example.com"]
            )
            self.assertEqual(
                state_after["notifications"]["email"].get("cooldown_minutes"), 5.0
            )

        self.assertIsNotNone(app.state.service.notifier)
        self.assertAlmostEqual(app.state.service.alert_cooldown_minutes, 5.0)

        app_without_sendgrid = create_app(
            root_dir=self.tmp_path / "datalake_notifications_no_sendgrid",
            normal_description="",
            normal_description_path=self.tmp_path / "normal_notify_no_sendgrid.txt",
            notification_settings=NotificationSettings(),
            notification_config_path=self.tmp_path / "notifications_no_sendgrid.json",
        )

        with TestClient(app_without_sendgrid) as client:
            response = client.post(
                "/ui/notifications",
                json={"email_enabled": True, "email_recipients": ["ops@example.com"]},
            )
            self.assertEqual(response.status_code, 400)


if __name__ == "__main__":
    unittest.main()
