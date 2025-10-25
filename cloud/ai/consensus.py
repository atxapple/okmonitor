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

        # Prepare agent details for storage
        agent_details = {
            "agent1": {
                "state": primary.state,
                "score": primary.score,
                "reason": primary.reason,
            },
            "agent2": {
                "state": secondary.state,
                "score": secondary.score,
                "reason": secondary.reason,
            },
        }

        if state != "uncertain" and score < LOW_CONFIDENCE_THRESHOLD:
            note = f"Average confidence {score:.2f} below threshold {LOW_CONFIDENCE_THRESHOLD:.2f}."
            reason_text = f"{reason_text} | {note}" if reason_text else note
            return Classification(
                state="uncertain", score=score, reason=reason_text, agent_details=agent_details
            )

        return Classification(state=state, score=score, reason=reason_text, agent_details=agent_details)

    def _mark_uncertain(
        self,
        primary: Classification,
        secondary: Classification,
    ) -> Classification:
        # Prepare agent details for storage
        agent_details = {
            "agent1": {
                "state": primary.state,
                "score": primary.score,
                "reason": primary.reason,
            },
            "agent2": {
                "state": secondary.state,
                "score": secondary.score,
                "reason": secondary.reason,
            },
        }

        # Prioritize reasoning from abnormal/uncertain agents over normal agents
        primary_state = primary.state.strip().lower()
        secondary_state = secondary.state.strip().lower()

        selected_reason = None

        # If one agent is abnormal/uncertain and has reasoning, prefer that
        if primary_state in ("abnormal", "uncertain") and primary.reason:
            selected_reason = primary.reason
        elif secondary_state in ("abnormal", "uncertain") and secondary.reason:
            selected_reason = secondary.reason
        # Otherwise, fall back to highest confidence agent
        elif primary.score >= secondary.score:
            selected_reason = primary.reason
        else:
            selected_reason = secondary.reason

        # Format with "Low confidence" prefix
        if selected_reason:
            reason_text = f"Low confidence: {selected_reason}"
        else:
            reason_text = "Low confidence"

        score = min(primary.score, secondary.score)
        return Classification(state="uncertain", score=score, reason=reason_text, agent_details=agent_details)


__all__ = ["ConsensusClassifier"]
