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
            # Show only the highest confidence agent's reason
            if primary.score > secondary.score:
                reason_text = self._format_reason(self.primary_label, primary)
            elif secondary.score > primary.score:
                reason_text = self._format_reason(self.secondary_label, secondary)
            else:
                # Equal confidence: prefer Agent1 (primary)
                reason_text = self._format_reason(self.primary_label, primary)

            if not reason_text:
                reason_text = "Both classifiers flagged the capture as abnormal."
        elif state == "uncertain":
            # Show only the highest confidence agent's reason
            if primary.score > secondary.score:
                reason_text = self._format_reason(self.primary_label, primary)
            elif secondary.score > primary.score:
                reason_text = self._format_reason(self.secondary_label, secondary)
            else:
                # Equal confidence: prefer Agent1 (primary)
                reason_text = self._format_reason(self.primary_label, primary)
        else:
            reason_text = primary.reason or secondary.reason

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
        # Show only the highest confidence agent's reason
        if primary.score > secondary.score:
            highest_confidence_reason = self._format_reason(self.primary_label, primary)
        elif secondary.score > primary.score:
            highest_confidence_reason = self._format_reason(self.secondary_label, secondary)
        else:
            # Equal confidence: prefer Agent1 (primary)
            highest_confidence_reason = self._format_reason(self.primary_label, primary)

        reason_parts: list[str] = []
        if highest_confidence_reason:
            reason_parts.append(highest_confidence_reason)
        reason_parts.append("Classifiers disagreed; marking capture as uncertain.")
        reason_text = " | ".join(reason_parts)

        score = min(primary.score, secondary.score)
        return Classification(state="uncertain", score=score, reason=reason_text)

    @staticmethod
    def _merge_optional_text(first: str | None, second: str | None) -> str | None:
        parts = [text for text in (first, second) if text]
        if not parts:
            return None
        unique_parts: list[str] = []
        for entry in parts:
            if entry not in unique_parts:
                unique_parts.append(entry)
        return " | ".join(unique_parts)

    @staticmethod
    def _format_reason(label: str, classification: Classification) -> str | None:
        reason = classification.reason
        if reason:
            return f"{label}: {reason}"
        state = classification.state.strip().lower()
        if not state:
            return None
        return f"{label} classified capture as {state}."


__all__ = ["ConsensusClassifier"]
