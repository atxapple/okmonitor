import base64
import json
import unittest
from unittest.mock import Mock, patch

from cloud.ai.openai_client import OpenAIImageClassifier


class OpenAIImageClassifierTests(unittest.TestCase):
    def test_classify_parses_response_and_builds_payload(self) -> None:
        classifier = OpenAIImageClassifier(
            api_key="test-key",
            normal_description="Normal images show a green indicator light.",
        )
        image_bytes = b"binary-image"
        expected_b64 = base64.b64encode(image_bytes).decode("ascii")

        response_payload = {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "state": "Abnormal",
                                "confidence": 0.82,
                                "reason": "Indicator light is dark.",
                            }
                        )
                    }
                }
            ]
        }
        mock_response = Mock()
        mock_response.json.return_value = response_payload
        mock_response.raise_for_status.return_value = None

        fake_requests = Mock()
        fake_requests.post.return_value = mock_response

        with patch("cloud.ai.openai_client.requests", fake_requests):
            result = classifier.classify(image_bytes)

        self.assertEqual(result.state, "abnormal")
        self.assertAlmostEqual(result.score, 0.82)
        self.assertEqual(result.reason, "Indicator light is dark.")
        fake_requests.post.assert_called_once()

        url, kwargs = fake_requests.post.call_args
        self.assertTrue(url[0].endswith("/chat/completions"))
        payload = kwargs["json"]
        self.assertEqual(payload["model"], "gpt-4o-mini")
        self.assertEqual(payload["response_format"], {"type": "json_object"})

        user_content = payload["messages"][1]["content"]
        self.assertEqual(user_content[0]["type"], "text")
        user_text = user_content[0]["text"]
        self.assertIn("Normal, Abnormal, or Unexpected", user_text)
        self.assertIn("'reason'", user_text)
        self.assertEqual(user_content[1]["type"], "image_url")
        self.assertEqual(user_content[1]["image_url"]["url"], f"data:image/jpeg;base64,{expected_b64}")

    def test_classify_normalizes_state_and_score_defaults(self) -> None:
        classifier = OpenAIImageClassifier(api_key="test-key")
        response_payload = {
            "choices": [
                {"message": {"content": json.dumps({"label": "UNEXPECTED", "score": "0.15"})}}
            ]
        }
        mock_response = Mock()
        mock_response.json.return_value = response_payload
        mock_response.raise_for_status.return_value = None

        fake_requests = Mock()
        fake_requests.post.return_value = mock_response

        with patch("cloud.ai.openai_client.requests", fake_requests):
            result = classifier.classify(b"image")

        self.assertEqual(result.state, "unexpected")
        self.assertAlmostEqual(result.score, 0.15)
        self.assertIsNone(result.reason)


if __name__ == "__main__":
    unittest.main()
