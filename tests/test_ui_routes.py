import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from cloud.api.server import create_app


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

            update = client.post("/ui/normal-description", json={"description": "Updated"})
            self.assertEqual(update.status_code, 200)
            self.assertEqual(update.json()["normal_description"], "Updated")
            self.assertTrue(normal_path.exists())
            self.assertEqual(normal_path.read_text(encoding="utf-8"), "Updated")

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

            image_resp = client.get(f"/ui/captures/{record.record_id}/image")
            self.assertEqual(image_resp.status_code, 200)
            self.assertTrue(image_resp.headers["content-type"].startswith("image/"))

            enable = client.post('/ui/trigger', json={'enabled': True, 'interval_seconds': 5})
            self.assertEqual(enable.status_code, 200)
            self.assertTrue(enable.json()['trigger']['enabled'])

            disable = client.post('/ui/trigger', json={'enabled': False, 'interval_seconds': None})
            self.assertEqual(disable.status_code, 200)
            self.assertFalse(disable.json()['trigger']['enabled'])

            config_resp = client.get('/v1/device-config')
            self.assertEqual(config_resp.status_code, 200)
            config_payload = config_resp.json()
            self.assertEqual(config_payload['device_id'], 'ui-device')
            self.assertEqual(config_payload['trigger'], {'enabled': False, 'interval_seconds': None})


if __name__ == "__main__":
    unittest.main()
