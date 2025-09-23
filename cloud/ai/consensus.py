from __future__ import annotations

from dataclasses import dataclass

from .types import Classification, Classifier


@dataclass
class ConsensusClassifier(Classifier):
    """Combine two classifiers and reconcile their predictions."""

    primary: Classifier
    secondary: Classifier
    primary_label: str = "OpenAI"
    secondary_label: str = "Gemini"

    def classify(self, image_bytes: bytes) -> Classification:
        primary_result = self.primary.classify(image_bytes)
        secondary_result = self.secondary.classify(image_bytes)

        primary_state = primary_result.state.strip().lower()
        secondary_state = secondary_result.state.strip().lower()

        if primary_state == secondary_state:
            return self._combine_consistent(primary_result, secondary_result)

        return self._resolve_inconsistency(primary_result, secondary_result)

    def _combine_consistent(
        self,
        primary: Classification,
        secondary: Classification,
    ) -> Classification:
        state = primary.state.strip().lower()
        score = (primary.score + secondary.score) / 2.0

        if state == "abnormal":
            reasons: list[str] = []
            if primary.reason:
                reasons.append(f"{self.primary_label}: {primary.reason}")
            if secondary.reason:
                entry = f"{self.secondary_label}: {secondary.reason}"
                if entry not in reasons:
                    reasons.append(entry)
            if reasons:
                reason_text = " | ".join(reasons)
            else:
                reason_text = "Both classifiers flagged the capture as abnormal."
        else:
            reason_text = primary.reason or secondary.reason

        return Classification(state=state, score=score, reason=reason_text)

    def _resolve_inconsistency(
        self,
        primary: Classification,
        secondary: Classification,
    ) -> Classification:
        first = (primary, self.primary_label)
        second = (secondary, self.secondary_label)
        best, other = self._select_preferred(first, second)
        best_state = best[0].state.strip().lower()

        reason_parts: list[str] = []
        if best[0].reason:
            reason_parts.append(f"{best[1]}: {best[0].reason}")
        else:
            reason_parts.append(f"{best[1]} classified capture as {best[0].state}.")
        reason_parts.append(f"{other[1]} classified capture as {other[0].state}.")
        reason_text = " ".join(reason_parts)

        return Classification(state=best_state, score=best[0].score, reason=reason_text)

    @staticmethod
    def _severity(state: str) -> int:
        label = state.strip().lower()
        priority = {"abnormal": 3, "unexpected": 2, "normal": 1}
        return priority.get(label, 0)

    def _select_preferred(
        self,
        first: tuple[Classification, str],
        second: tuple[Classification, str],
    ) -> tuple[tuple[Classification, str], tuple[Classification, str]]:
        first_severity = self._severity(first[0].state)
        second_severity = self._severity(second[0].state)

        if first_severity > second_severity:
            return first, second
        if second_severity > first_severity:
            return second, first
        # Equal severity; prefer higher confidence
        if second[0].score > first[0].score:
            return second, first
        return first, second


__all__ = ["ConsensusClassifier"]
