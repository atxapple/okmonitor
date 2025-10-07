from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from typing import Any

try:  # pragma: no cover - optional dependency for static analysis
    import requests  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover - handled at runtime below
    requests = None  # type: ignore[assignment]

from .types import Classification, Classifier, LOW_CONFIDENCE_THRESHOLD


@dataclass
class OpenAIImageClassifier(Classifier):
    """Classify captures by delegating to the OpenAI multimodal chat API."""

    api_key: str
    model: str = "gpt-4o-mini"
    base_url: str = "https://api.openai.com/v1"
    normal_description: str = ""
    timeout: float = 30.0

    def classify(self, image_bytes: bytes) -> Classification:
        if not self.api_key:
            raise RuntimeError("OpenAI API key is required to classify captures")

        payload = self._build_payload(image_bytes)
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        url = f"{self.base_url.rstrip('/')}/chat/completions"
        data = self._send_request(url, payload, headers)
        message = self._extract_message_content(data)
        return self._parse_message(message)

    def _send_request(
        self, url: str, payload: dict[str, Any], headers: dict[str, str]
    ) -> dict[str, Any]:
        if requests is None:
            raise RuntimeError(
                "The 'requests' package is required to call the OpenAI API. Install it to enable the classifier."
            )
        try:
            response = requests.post(
                url, json=payload, headers=headers, timeout=self.timeout
            )
            response.raise_for_status()
            return response.json()
        except (
            Exception
        ) as exc:  # pragma: no cover - network failure surfaced to caller
            raise RuntimeError(f"Failed to reach OpenAI API: {exc}") from exc

    def _build_payload(self, image_bytes: bytes) -> dict[str, Any]:
        prompt = self._build_prompt()
        encoded = base64.b64encode(image_bytes).decode("ascii")
        data_url = f"data:image/jpeg;base64,{encoded}"
        return {
            "model": self.model,
            "response_format": {"type": "json_object"},
            "temperature": 0.0,
            "messages": [
                {
                    "role": "system",
                    "content": self._system_prompt(),
                },
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": data_url}},
                    ],
                },
            ],
        }

    def _system_prompt(self) -> str:
        return (
            "You are an inspection classifier for machine captures. "
            "Analyse each image and decide whether it is Normal, Abnormal, or Uncertain. "
            "Only respond with JSON describing your decision."
        )

    def _build_prompt(self) -> str:
        description = (
            self.normal_description.strip() or "No normal description provided."
        )
        return (
            "Use the following description of a normal capture as context:\n"
            f"{description}\n\n"
            "Label the supplied image as one of: Normal, Abnormal, or Uncertain.\n"
            "Return a JSON object with fields 'state' (lowercase label), 'confidence' (float between 0 and 1), "
            "and 'reason' (short explanation for abnormal results; use null for other states)."
        )

    def _extract_message_content(self, data: dict[str, Any]) -> str:
        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError("Unexpected response format from OpenAI API") from exc

    def _parse_message(self, message: str) -> Classification:
        try:
            payload = json.loads(message)
        except json.JSONDecodeError as exc:
            raise RuntimeError("OpenAI API response was not valid JSON") from exc

        raw_state = payload.get("state") or payload.get("label")
        if not raw_state:
            raise RuntimeError("OpenAI API response did not include a state")
        state = self._normalize_state(str(raw_state))

        score_value = payload.get("confidence", payload.get("score", 0.0))
        try:
            score = float(score_value)
        except (TypeError, ValueError):
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

        if state == "abnormal" and reason is None:
            reason = "Model marked capture as abnormal but did not provide details."

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


__all__ = ["OpenAIImageClassifier"]
