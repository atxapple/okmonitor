from __future__ import annotations

import base64
import json
import logging
from dataclasses import dataclass
from typing import Any

try:  # pragma: no cover - optional dependency for static analysis
    import requests  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover - handled at runtime below
    requests = None  # type: ignore[assignment]

from .types import Classification, Classifier, LOW_CONFIDENCE_THRESHOLD


logger = logging.getLogger(__name__)


@dataclass
class GeminiImageClassifier(Classifier):
    """Classify captures by delegating to the Google Gemini multimodal API."""

    api_key: str
    model: str = "models/gemini-2.5-flash"
    base_url: str = "https://generativelanguage.googleapis.com/v1beta"
    timeout: float = 30.0
    normal_description: str = ""

    def classify(self, image_bytes: bytes) -> Classification:
        if not self.api_key:
            raise RuntimeError("Gemini API key is required to classify captures")

        payload = self._build_payload(image_bytes)
        url = f"{self.base_url.rstrip('/')}/{self.model}:generateContent"
        logger.info(
            "Gemini classify start model=%s image_bytes=%d",
            self.model,
            len(image_bytes),
        )
        try:
            response_data = self._send_request(url, payload)
        except RuntimeError as exc:
            logger.exception("Gemini classify request failed: %s", exc)
            raise
        message = self._extract_message_content(response_data)
        logger.debug("Gemini response snippet: %s", message[:200])
        classification = self._parse_message(message)
        logger.info(
            "Gemini classify complete state=%s score=%.2f",
            classification.state,
            classification.score,
        )
        return classification

    def _send_request(self, url: str, payload: dict[str, Any]) -> dict[str, Any]:
        if requests is None:
            raise RuntimeError(
                "The 'requests' package is required to call the Gemini API. Install it to enable the classifier."
            )
        try:
            logger.info("Calling Gemini API url=%s model=%s", url, self.model)
            response = requests.post(
                url,
                params={"key": self.api_key},
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=self.timeout,
            )
            response.raise_for_status()
            logger.debug(
                "Gemini API response status=%s headers=%s",
                response.status_code,
                {
                    "content-type": response.headers.get("content-type", ""),
                    "x-request-id": response.headers.get("x-request-id"),
                },
            )
            return response.json()
        except Exception as exc:  # pragma: no cover - surfaced to caller
            logger.exception("Failed Gemini API request: %s", exc)
            raise RuntimeError(f"Failed to reach Gemini API: {exc}") from exc

    def _build_payload(self, image_bytes: bytes) -> dict[str, Any]:
        description = self._build_prompt()
        encoded = base64.b64encode(image_bytes).decode("ascii")
        return {
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {"text": description},
                        {
                            "inline_data": {
                                "mime_type": "image/jpeg",
                                "data": encoded,
                            }
                        },
                    ],
                }
            ],
            "generationConfig": {
                "temperature": 0.0,
                "responseMimeType": "application/json",
            },
        }

    def _build_prompt(self) -> str:
        description = (
            self.normal_description.strip() or "No normal description provided."
        )
        return (
            "You are an inspection classifier for machine captures. "
            "Use the following description of a normal capture as context:\n"
            f"{description}\n\n"
            "Label the supplied image as one of: Normal, Abnormal, or Uncertain.\n"
            "Return a JSON object with fields 'state' (lowercase label), 'confidence' (float between 0 and 1), "
            "and 'reason' (short explanation for abnormal results; use null for other states)."
        )

    def _extract_message_content(self, data: dict[str, Any]) -> str:
        try:
            parts = data["candidates"][0]["content"]["parts"]
            return "".join(part.get("text", "") for part in parts)
        except (KeyError, IndexError, TypeError) as exc:
            logger.exception("Unexpected Gemini response structure: %s", exc)
            raise RuntimeError("Unexpected response format from Gemini API") from exc

    def _parse_message(self, message: str) -> Classification:
        try:
            payload = json.loads(message)
        except json.JSONDecodeError as exc:
            logger.exception("Gemini response was not valid JSON: %s", exc)
            raise RuntimeError("Gemini API response was not valid JSON") from exc

        raw_state = payload.get("state") or payload.get("label")
        if not raw_state:
            logger.error("Gemini response missing state field: %s", payload)
            raise RuntimeError("Gemini API response did not include a state")
        state = self._normalize_state(str(raw_state))

        score_value = payload.get("confidence", payload.get("score", 0.0))
        try:
            score = float(score_value)
        except (TypeError, ValueError):
            logger.warning("Gemini provided non-numeric confidence '%s'", score_value)
            score = 0.0
        score = max(0.0, min(1.0, score))

        reason_value = payload.get("reason")
        reason = None
        if isinstance(reason_value, str):
            reason = reason_value.strip() or None

        low_confidence_note = None
        if score < LOW_CONFIDENCE_THRESHOLD:
            state = "uncertain"
            low_confidence_note = f"Classifier confidence {score:.2f} below threshold {LOW_CONFIDENCE_THRESHOLD:.2f}."
            logger.warning(
                "Gemini classification downgraded to uncertain: %s", low_confidence_note
            )

        if state == "abnormal" and reason is None:
            reason = "Model marked capture as abnormal but did not provide details."
            logger.debug("Gemini abnormal without reason; inserting default text")

        if low_confidence_note:
            reason = (
                f"{reason} | {low_confidence_note}" if reason else low_confidence_note
            )

        return Classification(state=state, score=score, reason=reason)

    def _normalize_state(self, value: str) -> str:
        label = value.strip().lower()
        if label == "unexpected":
            return "uncertain"
        if label in {"normal", "abnormal", "uncertain"}:
            return label
        if "abnormal" in label or "alert" in label:
            return "abnormal"
        if any(
            term in label
            for term in ("unexpected", "unknown", "uncertain", "uncertainty")
        ):
            return "uncertain"
        return "normal"


__all__ = ["GeminiImageClassifier"]
