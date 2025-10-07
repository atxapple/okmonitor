from __future__ import annotations

import base64
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Any, Dict

from ..ai import Classifier
from ..datalake.storage import FileSystemDatalake, CaptureRecord
from .capture_index import RecentCaptureIndex
from .email_service import AbnormalCaptureNotifier


logger = logging.getLogger(__name__)


@dataclass
class _DedupeEntry:
    state: str = ""
    count: int = 0
    last_record_id: str | None = None


@dataclass
class _StreakEntry:
    state: str = ""
    count: int = 0
    post_threshold_counter: int = 0


@dataclass
class InferenceService:
    classifier: Classifier
    datalake: FileSystemDatalake
    capture_index: RecentCaptureIndex | None = None
    notifier: AbnormalCaptureNotifier | None = None
    normal_description_file: str | None = None
    alert_cooldown_minutes: float = 0.0
    dedupe_enabled: bool = False
    dedupe_threshold: int = 3
    dedupe_keep_every: int = 5
    streak_pruning_enabled: bool = False
    streak_threshold: int = 0
    streak_keep_every: int = 1
    _last_abnormal_sent: Dict[str, datetime] = field(init=False, default_factory=dict)
    _dedupe_tracker: Dict[str, _DedupeEntry] = field(init=False, default_factory=dict)
    _streak_tracker: Dict[str, _StreakEntry] = field(init=False, default_factory=dict)

    def __post_init__(self) -> None:
        self.update_alert_cooldown(self.alert_cooldown_minutes)
        self.update_dedupe_settings(
            self.dedupe_enabled, self.dedupe_threshold, self.dedupe_keep_every
        )
        self.update_streak_settings(
            self.streak_pruning_enabled, self.streak_threshold, self.streak_keep_every
        )

    def process_capture(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        image_b64: str = payload["image_base64"]
        try:
            image_bytes = base64.b64decode(image_b64)
        except Exception as exc:
            logger.exception("Failed to decode image payload: %s", exc)
            raise RuntimeError("Invalid base64 image payload") from exc

        logger.info(
            "Running inference device=%s trigger=%s image_bytes=%d",
            payload.get("device_id"),
            payload.get("trigger_label"),
            len(image_bytes),
        )

        classification = self.classifier.classify(image_bytes)
        logger.info(
            "Inference complete device=%s state=%s score=%.2f",
            payload.get("device_id"),
            classification.state,
            classification.score,
        )

        metadata = {
            "device_id": payload["device_id"],
            "trigger_label": payload["trigger_label"],
            **payload.get("metadata", {}),
        }
        classification_payload = {
            "state": classification.state,
            "score": classification.score,
            "reason": classification.reason,
        }
        device_key = self._device_key(metadata)
        state_label = str(classification.state or "").strip().lower()
        streak_store_image = True
        if self.streak_pruning_enabled:
            streak_store_image = self._should_store_image(device_key, state_label)
        else:
            self._streak_tracker.pop(device_key, None)

        dedupe_entry = None
        store_capture = True
        if self.dedupe_enabled:
            store_capture, dedupe_entry = self._should_store_state(
                device_key, state_label
            )
        else:
            self._dedupe_tracker.pop(device_key, None)

        stored_record: CaptureRecord | None = None
        record_id_for_response: str | None = None

        if store_capture or dedupe_entry is None or dedupe_entry.last_record_id is None:
            stored_record = self.datalake.store_capture(
                image_bytes=image_bytes if streak_store_image else None,
                metadata=metadata,
                classification=classification_payload,
                normal_description_file=self.normal_description_file,
                store_image=streak_store_image,
            )
            record_id_for_response = stored_record.record_id
            if dedupe_entry is not None:
                dedupe_entry.last_record_id = stored_record.record_id
            if self.capture_index is not None:
                self.capture_index.add_record(stored_record)
            if not stored_record.image_stored:
                streak_entry = self._streak_tracker.get(device_key)
                streak_count = streak_entry.count if streak_entry else 0
                logger.info(
                    "Streak pruning stored metadata without image device=%s state=%s streak=%d threshold=%d keep_every=%d",
                    device_key,
                    state_label,
                    streak_count,
                    self.streak_threshold,
                    self.streak_keep_every,
                )
        else:
            record_id_for_response = dedupe_entry.last_record_id
            logger.debug(
                "Skipping capture storage due to dedupe device=%s state=%s count=%d",
                device_key,
                state_label,
                dedupe_entry.count,
            )

        device_key = self._device_key(metadata)
        state_label = str(classification.state or "").strip().lower()
        if state_label == "normal":
            self._last_abnormal_sent.pop(device_key, None)
        elif state_label == "abnormal" and self.notifier is not None:
            if stored_record is not None and self._should_send_abnormal(device_key):
                try:
                    self.notifier.notify_abnormal(stored_record)
                except Exception:
                    logger.exception(
                        "Failed to send abnormal notification record_id=%s",
                        stored_record.record_id,
                    )
            elif stored_record is None:
                logger.info(
                    "Suppressing abnormal alert due to dedupe device=%s state=%s",
                    device_key,
                    state_label,
                )
            else:
                logger.info(
                    "Suppressing abnormal alert due to cooldown device=%s window=%.2f minute(s)",
                    device_key,
                    self.alert_cooldown_minutes,
                )
        logger.debug(
            "Processed capture record_id=%s metadata_keys=%s",
            (stored_record.record_id if stored_record else record_id_for_response),
            sorted(metadata.keys()),
        )
        return {
            "record_id": record_id_for_response or "",
            **classification_payload,
        }

    def update_alert_cooldown(self, minutes: float) -> None:
        sanitized = max(0.0, float(minutes or 0.0))
        self.alert_cooldown_minutes = sanitized
        if sanitized <= 0:
            self._last_abnormal_sent.clear()

    def update_dedupe_settings(
        self, enabled: bool, threshold: int, keep_every: int
    ) -> None:
        self.dedupe_enabled = bool(enabled)
        self.dedupe_threshold = max(0, int(threshold or 0))
        self.dedupe_keep_every = max(1, int(keep_every or 1))
        if not self.dedupe_enabled:
            self._dedupe_tracker.clear()

    def update_streak_settings(
        self, enabled: bool, threshold: int, keep_every: int
    ) -> None:
        self.streak_pruning_enabled = bool(enabled)
        self.streak_threshold = max(0, int(threshold or 0))
        self.streak_keep_every = max(1, int(keep_every or 1))
        if not self.streak_pruning_enabled:
            self._streak_tracker.clear()

    def _should_store_state(
        self, device_key: str, state_label: str
    ) -> tuple[bool, _DedupeEntry]:
        entry = self._dedupe_tracker.get(device_key)
        if entry is None:
            entry = _DedupeEntry()
        if not state_label:
            entry.state = state_label
            entry.count = 1 if state_label else 0
            self._dedupe_tracker[device_key] = entry
            return True, entry
        if entry.state == state_label:
            entry.count += 1
        else:
            entry.state = state_label
            entry.count = 1
            entry.last_record_id = None
        self._dedupe_tracker[device_key] = entry
        threshold = max(0, self.dedupe_threshold)
        keep_every = max(1, self.dedupe_keep_every)
        if entry.count <= threshold:
            return True, entry
        should_store = (entry.count - threshold - 1) % keep_every == 0
        return should_store, entry

    def _should_store_image(self, device_key: str, state_label: str) -> bool:
        entry = self._streak_tracker.get(device_key)
        if entry is None:
            entry = _StreakEntry()
        if not state_label:
            entry.state = state_label
            entry.count = 1 if state_label else 0
            entry.post_threshold_counter = 0
            self._streak_tracker[device_key] = entry
            return True
        if entry.state == state_label:
            entry.count += 1
        else:
            entry.state = state_label
            entry.count = 1
            entry.post_threshold_counter = 0
        self._streak_tracker[device_key] = entry

        threshold = max(0, self.streak_threshold)
        keep_every = max(1, self.streak_keep_every)
        if threshold <= 0 or entry.count <= threshold:
            entry.post_threshold_counter = 0
            return True

        entry.post_threshold_counter += 1
        if entry.post_threshold_counter % keep_every == 0:
            return True
        return False

    def _should_send_abnormal(self, device_key: str) -> bool:
        cooldown = self.alert_cooldown_minutes
        now = datetime.now(timezone.utc)
        last = self._last_abnormal_sent.get(device_key)
        if cooldown <= 0 or last is None or now - last >= timedelta(minutes=cooldown):
            self._last_abnormal_sent[device_key] = now
            return True
        return False

    def _device_key(self, metadata: Dict[str, Any]) -> str:
        value = metadata.get("device_id") if isinstance(metadata, dict) else None
        return (
            str(value) if value is not None and str(value).strip() else "unknown-device"
        )


__all__ = ["InferenceService"]
