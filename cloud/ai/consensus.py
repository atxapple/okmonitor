from __future__ import annotations

from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor

from .types import Classification, Classifier, LOW_CONFIDENCE_THRESHOLD


_CLASSIFY_EXECUTOR = ThreadPoolExecutor(max_workers=4)


@dataclass
class ConsensusClassifier(Classifier):
    """Combine two classifiers and reconcile their predictions."""

    primary: Classifier
    secondary: Classifier
    primary_label: str = "Agent1"
    secondary_label: str = "Agent2"

    def classify(self, image_bytes: bytes) -> Classification:
        future_primary = _CLASSIFY_EXECUTOR.submit(self.primary.classify, image_bytes)
        future_secondary = _CLASSIFY_EXECUTOR.submit(
            self.secondary.classify, image_bytes
        )

        try:
            primary_result = future_primary.result()
        except Exception as exc:
            # If primary fails, cancel secondary and wait for cleanup
            future_secondary.cancel()
            # Attempt to get result with short timeout to ensure cleanup
            # This prevents thread/resource leaks from abandoned futures
            try:
                future_secondary.result(timeout=1.0)
            except Exception:
                # Ignore secondary errors since primary already failed
                pass
            raise

        # Primary succeeded, now get secondary result
        # If secondary fails, we still want to raise the exception
        secondary_result = future_secondary.result()

        primary_state = primary_result.state.strip().lower()
        secondary_state = secondary_result.state.strip().lower()

        if primary_state == secondary_state:
            return self._combine_consistent(primary_result, secondary_result)

        return self._mark_uncertain(primary_result, secondary_result)

    def _combine_consistent(
        self,
        primary: Classification,
        secondary: Classification,
    ) -> Classification:
        state = primary.state.strip().lower()
        score = (primary.score + secondary.score) / 2.0

        reason_text: str | None
        if state == "abnormal":
            # Show only the highest confidence agent's reason (without label)
            if primary.score > secondary.score:
                reason_text = primary.reason
            elif secondary.score > primary.score:
                reason_text = secondary.reason
            else:
                # Equal confidence: prefer Agent1 (primary)
                reason_text = primary.reason

            if not reason_text:
                reason_text = "Both classifiers flagged the capture as abnormal."
        elif state == "uncertain":
            # Show only the highest confidence agent's reason (without label)
            if primary.score > secondary.score:
                reason_text = primary.reason
            elif secondary.score > primary.score:
                reason_text = secondary.reason
            else:
                # Equal confidence: prefer Agent1 (primary)
                reason_text = primary.reason
        else:
            # Normal state: don't show reason
            reason_text = None

        if state != "uncertain" and score < LOW_CONFIDENCE_THRESHOLD:
            note = f"Average confidence {score:.2f} below threshold {LOW_CONFIDENCE_THRESHOLD:.2f}."
            reason_text = f"{reason_text} | {note}" if reason_text else note
            return Classification(state="uncertain", score=score, reason=reason_text)

        return Classification(state=state, score=score, reason=reason_text)

    def _mark_uncertain(
        self,
        primary: Classification,
        secondary: Classification,
    ) -> Classification:
        # Determine which agent has higher confidence
        if primary.score > secondary.score:
            highest_confidence_agent = primary
            other_agent = secondary
        elif secondary.score > primary.score:
            highest_confidence_agent = secondary
            other_agent = primary
        else:
            # Equal confidence: prefer Agent1 (primary)
            highest_confidence_agent = primary
            other_agent = secondary

        # If highest confidence is normal, use the other agent's reason
        # (since normal doesn't have meaningful reasoning)
        highest_state = highest_confidence_agent.state.strip().lower()
        if highest_state == "normal":
            selected_reason = other_agent.reason
        else:
            selected_reason = highest_confidence_agent.reason

        # Format with "Low confidence" prefix
        if selected_reason:
            reason_text = f"Low confidence: {selected_reason}"
        else:
            reason_text = "Low confidence"

        score = min(primary.score, secondary.score)
        return Classification(state="uncertain", score=score, reason=reason_text)


__all__ = ["ConsensusClassifier"]
