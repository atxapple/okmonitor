import base64
import json
import unittest
from unittest.mock import Mock, patch

from cloud.ai.nim_client import NIMImageClassifier
from cloud.ai.types import LOW_CONFIDENCE_THRESHOLD


class NIMImageClassifierTests(unittest.TestCase):
    def test_classify_parses_response_and_adds_safety_settings(self) -> None:
        classifier = NIMImageClassifier(
            api_key="nv-token",
            normal_description="Normal image shows a green LED lit.",
        )
        image_bytes = b"binary"
        expected_b64 = base64.b64encode(image_bytes).decode("ascii")
        payload = {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "state": "abnormal",
                                "confidence": 0.87,
                                "reason": "The LED is off.",
                            }
                        )
                    }
                }
            ]
        }
        mock_response = Mock()
        mock_response.json.return_value = payload
        mock_response.raise_for_status.return_value = None

        fake_requests = Mock()
        fake_requests.post.return_value = mock_response

        with patch("cloud.ai.nim_client.requests", fake_requests):
            result = classifier.classify(image_bytes)

        self.assertEqual(result.state, "abnormal")
        self.assertAlmostEqual(result.score, 0.87)
        self.assertEqual(result.reason, "The LED is off.")

        url, kwargs = fake_requests.post.call_args
        self.assertTrue(url[0].endswith("/chat/completions"))
        payload_sent = kwargs["json"]
        self.assertEqual(payload_sent["model"], classifier.model)
        self.assertEqual(payload_sent["response_format"], {"type": "json_object"})
        self.assertEqual(
            payload_sent.get("safety_settings"),
            {"vision": "BLOCK_NONE", "text": "BLOCK_NONE"},
        )
        user_content = payload_sent["messages"][1]["content"]
        self.assertEqual(
            user_content[1]["image_url"]["url"],
            f"data:image/jpeg;base64,{expected_b64}",
        )

    def test_low_confidence_marks_uncertain(self) -> None:
        classifier = NIMImageClassifier(api_key="nv-token")
        payload = {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {"state": "normal", "confidence": 0.01, "reason": None}
                        )
                    }
                }
            ]
        }
        mock_response = Mock()
        mock_response.json.return_value = payload
        mock_response.raise_for_status.return_value = None

        fake_requests = Mock()
        fake_requests.post.return_value = mock_response

        with patch("cloud.ai.nim_client.requests", fake_requests):
            result = classifier.classify(b"image")

        self.assertEqual(result.state, "uncertain")
        self.assertIsNotNone(result.reason)
        self.assertIn(f"{LOW_CONFIDENCE_THRESHOLD:.2f}", result.reason)


if __name__ == "__main__":
    unittest.main()
