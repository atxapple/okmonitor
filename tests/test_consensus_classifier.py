import unittest

from cloud.ai.consensus import ConsensusClassifier
from cloud.ai.types import Classification, Classifier


class _StaticClassifier(Classifier):
    def __init__(self, *, state: str, score: float, reason: str | None = None) -> None:
        self._classification = Classification(state=state, score=score, reason=reason)

    def classify(self, image_bytes: bytes) -> Classification:  # pragma: no cover - trivial forwarding
        return self._classification


class ConsensusClassifierTests(unittest.TestCase):
    def test_returns_average_when_states_match(self) -> None:
        primary = _StaticClassifier(state="normal", score=0.6, reason="ok")
        secondary = _StaticClassifier(state="normal", score=0.8, reason=None)
        classifier = ConsensusClassifier(primary=primary, secondary=secondary)

        result = classifier.classify(b"dummy")
        self.assertEqual(result.state, "normal")
        self.assertAlmostEqual(result.score, 0.7)
        self.assertEqual(result.reason, "ok")

    def test_combines_reasons_when_both_abnormal(self) -> None:
        primary = _StaticClassifier(state="abnormal", score=0.4, reason="issue detected")
        secondary = _StaticClassifier(state="abnormal", score=0.6, reason="defect spotted")
        classifier = ConsensusClassifier(primary=primary, secondary=secondary)

        result = classifier.classify(b"dummy")
        self.assertEqual(result.state, "abnormal")
        self.assertAlmostEqual(result.score, 0.5)
        self.assertIn("OpenAI: issue detected", result.reason)
        self.assertIn("Gemini: defect spotted", result.reason)

    def test_prefers_abnormal_on_disagreement(self) -> None:
        primary = _StaticClassifier(state="normal", score=0.3)
        secondary = _StaticClassifier(state="abnormal", score=0.9, reason="anomaly")
        classifier = ConsensusClassifier(primary=primary, secondary=secondary)

        result = classifier.classify(b"dummy")
        self.assertEqual(result.state, "abnormal")
        self.assertEqual(result.score, 0.9)
        self.assertIn("Gemini: anomaly", result.reason)
        self.assertIn("OpenAI classified capture as normal", result.reason)


if __name__ == "__main__":
    unittest.main()
