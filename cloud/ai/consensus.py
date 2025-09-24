from __future__ import annotations

from dataclasses import dataclass

from .types import Classification, Classifier, LOW_CONFIDENCE_THRESHOLD


@dataclass
class ConsensusClassifier(Classifier):
    """Combine two classifiers and reconcile their predictions."""

    primary: Classifier
    secondary: Classifier
    primary_label: str = "Agent1"
    secondary_label: str = "Agent2"

    def classify(self, image_bytes: bytes) -> Classification:
        primary_result = self.primary.classify(image_bytes)
        secondary_result = self.secondary.classify(image_bytes)

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
            reasons: list[str] = []
            formatted_primary = self._format_reason(self.primary_label, primary)
            formatted_secondary = self._format_reason(self.secondary_label, secondary)
            if formatted_primary:
                reasons.append(formatted_primary)
            if formatted_secondary and formatted_secondary not in reasons:
                reasons.append(formatted_secondary)
            if reasons:
                reason_text = " | ".join(reasons)
            else:
                reason_text = "Both classifiers flagged the capture as abnormal."
        elif state == "uncertain":
            reason_text = self._merge_optional_text(primary.reason, secondary.reason)
        else:
            reason_text = primary.reason or secondary.reason

        if state != "uncertain" and score < LOW_CONFIDENCE_THRESHOLD:
            note = (
                f"Average confidence {score:.2f} below threshold {LOW_CONFIDENCE_THRESHOLD:.2f}."
            )
            reason_text = (
                f"{reason_text} | {note}" if reason_text else note
            )
            return Classification(state="uncertain", score=score, reason=reason_text)

        return Classification(state=state, score=score, reason=reason_text)

    def _mark_uncertain(
        self,
        primary: Classification,
        secondary: Classification,
    ) -> Classification:
        reason_parts: list[str] = []
        formatted_primary = self._format_reason(self.primary_label, primary)
        formatted_secondary = self._format_reason(self.secondary_label, secondary)
        if formatted_primary:
            reason_parts.append(formatted_primary)
        if formatted_secondary:
            reason_parts.append(formatted_secondary)
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
