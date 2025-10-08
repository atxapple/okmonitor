from __future__ import annotations

import base64
import logging
import io
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Any, Dict

from PIL import Image

try:
    _RESAMPLE = Image.Resampling.LANCZOS  # type: ignore[attr-defined]
except AttributeError:  # pragma: no cover - Pillow < 9 fallback
    _RESAMPLE = Image.LANCZOS  # type: ignore[attr-defined]

from ..ai import Classifier
from ..ai.types import Classification
from ..datalake.storage import FileSystemDatalake, CaptureRecord
from .capture_index import RecentCaptureIndex
from .email_service import AbnormalCaptureNotifier
from .similarity_cache import CachedEvaluation, SimilarityCache


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
    similarity_enabled: bool = False
    similarity_threshold: int = 6
    similarity_expiry_minutes: float = 60.0
    similarity_cache: SimilarityCache | None = None
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
        if self.similarity_cache is not None:
            self.similarity_cache.prune_expired(self.similarity_expiry_minutes)

    def process_capture(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        image_b64: str = payload["image_base64"]
        try:
            image_bytes = base64.b64decode(image_b64)
        except Exception as exc:
            logger.exception("Failed to decode image payload: %s", exc)
            raise RuntimeError("Invalid base64 image payload") from exc

        device_key = self._device_key({"device_id": payload.get("device_id")})

        logger.info(
            "Running inference device=%s trigger=%s image_bytes=%d",
            payload.get("device_id"),
            payload.get("trigger_label"),
            len(image_bytes),
        )

        similarity_hash: str | None = None
        reused_entry: CachedEvaluation | None = None
        if self.similarity_enabled:
            similarity_hash = self._compute_similarity_hash(image_bytes)
            reused_entry = (
                self._maybe_reuse_classification(device_key, similarity_hash)
                if similarity_hash is not None
                else None
            )

        record_id_for_response: str | None = None
        if reused_entry is not None:
            classification = Classification(
                state=reused_entry.state,
                score=reused_entry.score,
                reason=reused_entry.reason,
            )
            record_id_for_response = reused_entry.record_id
            logger.info(
                "Reusing cached classification device=%s state=%s score=%.2f",
                payload.get("device_id"),
                classification.state,
                classification.score,
            )
        else:
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
        if self.streak_pruning_enabled or self.similarity_enabled:
            streak_store_image = self._should_store_image(device_key, state_label)
            if not self.streak_pruning_enabled:
                streak_store_image = True
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

        if (
            self.similarity_cache is not None
            and self.similarity_enabled
            and similarity_hash is not None
        ):
            cache_record_id = (
                stored_record.record_id
                if stored_record is not None
                else record_id_for_response
            )
            if cache_record_id:
                captured_at = stored_record.captured_at if stored_record else None
                self.similarity_cache.update(
                    device_id=device_key,
                    record_id=cache_record_id,
                    hash_hex=similarity_hash,
                    state=classification_payload["state"],
                    score=classification_payload["score"],
                    reason=classification_payload["reason"],
                    captured_at=captured_at,
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

    def _maybe_reuse_classification(
        self, device_key: str, hash_hex: str
    ) -> CachedEvaluation | None:
        if not self.similarity_enabled or self.similarity_cache is None:
            return None
        self.similarity_cache.prune_expired(self.similarity_expiry_minutes)
        if self.streak_threshold <= 0:
            return None
        streak_entry = self._streak_tracker.get(device_key)
        if (
            streak_entry is None
            or not streak_entry.state
            or streak_entry.count < self.streak_threshold
        ):
            return None
        cache_entry = self.similarity_cache.get(device_key)
        if cache_entry is None:
            return None
        if cache_entry.state != streak_entry.state:
            return None
        if cache_entry.is_expired(self.similarity_expiry_minutes):
            return None
        distance = _hamming_distance_hex(cache_entry.hash_hex, hash_hex)
        if distance > max(0, self.similarity_threshold):
            return None
        return cache_entry

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

    def _compute_similarity_hash(self, image_bytes: bytes) -> str | None:
        try:
            with Image.open(io.BytesIO(image_bytes)) as img:
                img = img.convert("L").resize((8, 8), _RESAMPLE)
                pixels = list(img.getdata())
        except Exception:
            logger.debug("Failed to compute similarity hash", exc_info=True)
            return None
        if not pixels:
            return None
        avg = sum(pixels) / len(pixels)
        bits = 0
        for value in pixels:
            bits = (bits << 1) | (1 if value >= avg else 0)
        return f"{bits:016x}"


__all__ = ["InferenceService"]


def _hamming_distance_hex(hex_a: str, hex_b: str) -> int:
    try:
        value_a = int(hex_a, 16)
        value_b = int(hex_b, 16)
    except ValueError:
        return 64
    diff = value_a ^ value_b
    return diff.bit_count()
