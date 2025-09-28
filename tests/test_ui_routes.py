import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from cloud.ai.consensus import ConsensusClassifier
from cloud.ai.types import Classification, Classifier
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
            self.assertEqual(data["device_id"], "ui-device")
            self.assertEqual(data["trigger"], {"enabled": False, "interval_seconds": None})
            self.assertEqual(data["manual_trigger_counter"], 0)
            status = data.get("device_status")
            self.assertIsNotNone(status)
            self.assertFalse(status["connected"])
            self.assertIsNone(status["last_seen"])
            self.assertIsNone(status["ip"])

            update = client.post("/ui/normal-description", json={"description": "Updated"})
            self.assertEqual(update.status_code, 200)
            self.assertEqual(update.json()["normal_description"], "Updated")
            self.assertTrue(normal_path.exists())
            self.assertEqual(normal_path.read_text(encoding="utf-8"), "Updated")

    def test_description_update_propagates_to_nested_classifiers(self) -> None:
        normal_path = self.tmp_path / "normal_nested.txt"
        consensus = ConsensusClassifier(primary=_DummyClassifier(), secondary=_DummyClassifier())
        app = create_app(
            root_dir=self.tmp_path / "datalake_nested",
            normal_description="Initial",
            normal_description_path=normal_path,
            classifier=consensus,
        )

        with TestClient(app) as client:
            response = client.post("/ui/normal-description", json={"description": "New guidance"})
            self.assertEqual(response.status_code, 200)
        self.assertEqual(consensus.primary.normal_description, "New guidance")
        self.assertEqual(consensus.secondary.normal_description, "New guidance")

    def test_device_id_validation_and_persistence(self) -> None:
        normal_path = self.tmp_path / "normal_device.txt"
        device_id_path = self.tmp_path / "device_id.txt"
        device_id_path.write_text("persisted-id\n", encoding="utf-8")
        app = create_app(
            root_dir=self.tmp_path / "datalake_device",
            normal_description="Initial",
            normal_description_path=normal_path,
            device_id_path=device_id_path,
        )

        with TestClient(app) as client:
            initial_state = client.get("/ui/state").json()
            self.assertEqual(initial_state["device_id"], "persisted-id")

            invalid = client.post("/ui/device-id", json={"device_id": " !! "})
            self.assertEqual(invalid.status_code, 422)

            valid = client.post("/ui/device-id", json={"device_id": "demo-device_2"})
            self.assertEqual(valid.status_code, 200)
            self.assertEqual(valid.json()["device_id"], "demo-device_2")

            self.assertEqual(device_id_path.read_text(encoding="utf-8"), "demo-device_2")

            refreshed = client.get("/ui/state").json()
            self.assertEqual(refreshed["device_id"], "demo-device_2")

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
            classification={"state": "abnormal", "score": 0.9, "reason": "Integration test"},
        )

        with TestClient(app) as client:
            captures = client.get("/ui/captures")
            self.assertEqual(captures.status_code, 200)
            payload = captures.json()
            self.assertTrue(payload, "Expected at least one capture")
            first = payload[0]
            self.assertEqual(first["record_id"], record.record_id)
            self.assertEqual(first["reason"], "Integration test")
            self.assertTrue(first.get("image_url"))
            self.assertTrue(first.get("download_url"))
            self.assertTrue(first["download_url"].endswith('?download=1'))

            image_resp = client.get(f"/ui/captures/{record.record_id}/image")
            self.assertEqual(image_resp.status_code, 200)
            self.assertTrue(image_resp.headers["content-type"].startswith("image/"))

            download_resp = client.get(f"/ui/captures/{record.record_id}/image", params={"download": "1"})
            self.assertEqual(download_resp.status_code, 200)
            self.assertIn('attachment', download_resp.headers.get('content-disposition', '').lower())

            enable = client.post('/ui/trigger', json={'enabled': True, 'interval_seconds': 5})
            self.assertEqual(enable.status_code, 200)
            self.assertTrue(enable.json()['trigger']['enabled'])

            disable = client.post('/ui/trigger', json={'enabled': False, 'interval_seconds': None})
            self.assertEqual(disable.status_code, 200)
            self.assertFalse(disable.json()['trigger']['enabled'])

            manual = client.post('/v1/manual-trigger')
            self.assertEqual(manual.status_code, 200)

            config_resp = client.get('/v1/device-config')
            self.assertEqual(config_resp.status_code, 200)
            config_payload = config_resp.json()
            self.assertEqual(config_payload['device_id'], 'ui-device')
            self.assertEqual(config_payload['trigger'], {'enabled': False, 'interval_seconds': None})
            self.assertGreaterEqual(config_payload['manual_trigger_counter'], 1)


if __name__ == "__main__":
    unittest.main()
