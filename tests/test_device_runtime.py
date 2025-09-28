import unittest

from device.main import update_device_identity


class DeviceRuntimeTests(unittest.TestCase):
    def test_update_device_identity_no_change_for_invalid_candidate(self) -> None:
        metadata = {"device_id": "alpha"}
        restarted: list[str] = []

        new_id = update_device_identity("alpha", "  ", metadata, restarted.append)

        self.assertEqual(new_id, "alpha")
        self.assertEqual(metadata["device_id"], "alpha")
        self.assertFalse(restarted)

    def test_update_device_identity_updates_metadata_and_restarts(self) -> None:
        metadata = {"device_id": "alpha"}
        restarted: list[str] = []
        logs: list[str] = []

        def log(message: str) -> None:
            logs.append(message)

        new_id = update_device_identity(
            "alpha",
            "beta-1",
            metadata,
            restarted.append,
            log=log,
        )

        self.assertEqual(new_id, "beta-1")
        self.assertEqual(metadata["device_id"], "beta-1")
        self.assertEqual(restarted, ["beta-1"])
        self.assertTrue(any("alpha" in entry and "beta-1" in entry for entry in logs))


if __name__ == "__main__":
    unittest.main()
