import unittest
import time

from cloud.ai.consensus import ConsensusClassifier
from cloud.ai.types import Classification, Classifier, LOW_CONFIDENCE_THRESHOLD


class _StaticClassifier(Classifier):
    def __init__(self, *, state: str, score: float, reason: str | None = None) -> None:
        self._classification = Classification(state=state, score=score, reason=reason)

    def classify(
        self, image_bytes: bytes
    ) -> Classification:  # pragma: no cover - trivial forwarding
        return self._classification


class _SlowClassifier(Classifier):
    def __init__(
        self, *, state: str, score: float, delay: float, reason: str | None = None
    ) -> None:
        self._classification = Classification(state=state, score=score, reason=reason)
        self._delay = delay

    def classify(self, image_bytes: bytes) -> Classification:
        time.sleep(self._delay)
        return self._classification


class ConsensusClassifierTests(unittest.TestCase):
    def test_returns_average_when_states_match(self) -> None:
        primary = _StaticClassifier(state="normal", score=0.6, reason="ok")
        secondary = _StaticClassifier(state="normal", score=0.8, reason=None)
        classifier = ConsensusClassifier(primary=primary, secondary=secondary)

        result = classifier.classify(b"dummy")
        self.assertEqual(result.state, "normal")
        self.assertAlmostEqual(result.score, 0.7)
        self.assertIsNone(result.reason)

    def test_combines_reasons_when_both_abnormal(self) -> None:
        primary = _StaticClassifier(
            state="abnormal", score=0.4, reason="issue detected"
        )
        secondary = _StaticClassifier(
            state="abnormal", score=0.6, reason="defect spotted"
        )
        classifier = ConsensusClassifier(primary=primary, secondary=secondary)

        result = classifier.classify(b"dummy")
        self.assertEqual(result.state, "uncertain")
        self.assertAlmostEqual(result.score, 0.5)
        # Should show only highest confidence agent's reason (secondary with 0.6)
        self.assertIn("defect spotted", result.reason)
        # Should NOT contain agent labels
        self.assertNotIn("Agent1", result.reason)
        self.assertNotIn("Agent2", result.reason)
        # Should contain low confidence note
        self.assertIn("Average confidence", result.reason)
        self.assertIn(f"{LOW_CONFIDENCE_THRESHOLD:.2f}", result.reason)

    def test_parallel_classification_runs_faster_than_sequential(self) -> None:
        primary = _SlowClassifier(state="normal", score=0.9, delay=0.3)
        secondary = _SlowClassifier(state="normal", score=0.9, delay=0.3)
        classifier = ConsensusClassifier(primary=primary, secondary=secondary)

        start = time.perf_counter()
        result = classifier.classify(b"payload")
        elapsed = time.perf_counter() - start

        self.assertEqual(result.state, "normal")
        self.assertLess(elapsed, 0.45)

    def test_marks_uncertain_on_disagreement(self) -> None:
        primary = _StaticClassifier(state="normal", score=0.3)
        secondary = _StaticClassifier(state="abnormal", score=0.9, reason="anomaly")
        classifier = ConsensusClassifier(primary=primary, secondary=secondary)

        result = classifier.classify(b"dummy")
        self.assertEqual(result.state, "uncertain")
        self.assertEqual(result.score, 0.3)
        # Should use "Low confidence:" prefix with highest confidence agent's reason
        # Since highest is secondary (abnormal, 0.9), use its reason
        self.assertEqual(result.reason, "Low confidence: anomaly")
        # Should NOT contain agent labels or old messaging
        self.assertNotIn("Agent1", result.reason)
        self.assertNotIn("Agent2", result.reason)
        self.assertNotIn("Classifiers disagreed", result.reason)


if __name__ == "__main__":
    unittest.main()
