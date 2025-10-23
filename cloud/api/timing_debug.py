"""
Timing debug infrastructure for analyzing end-to-end capture performance.

This module provides timing collection and statistics when ENABLE_TIMING_DEBUG is enabled.
Designed to be toggled on/off for debugging without production overhead.
"""
from __future__ import annotations

import logging
import statistics
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class CaptureTimings:
    """Timing data for a single capture, from device to UI."""

    record_id: str
    device_id: str

    # Device-side timestamps (UTC epoch seconds)
    t0_device_capture: float | None = None
    t1_device_thumbnail: float | None = None
    t2_device_request_sent: float | None = None

    # Server-side timestamps (UTC epoch seconds)
    t3_server_request_received: float | None = None
    t4_server_decode_complete: float | None = None
    t5_server_similarity_hash: float | None = None
    t6_server_inference_complete: float | None = None
    t7_server_storage_complete: float | None = None
    t8_server_broadcast_complete: float | None = None
    t9_server_response_sent: float | None = None

    # Metadata
    similarity_cache_hit: bool = False
    state: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def compute_deltas(self) -> dict[str, float | None]:
        """Compute time deltas between stages in milliseconds."""
        deltas = {}

        # Device stages
        if self.t0_device_capture and self.t1_device_thumbnail:
            deltas["device_thumbnail_ms"] = (self.t1_device_thumbnail - self.t0_device_capture) * 1000

        if self.t1_device_thumbnail and self.t2_device_request_sent:
            deltas["device_send_prep_ms"] = (self.t2_device_request_sent - self.t1_device_thumbnail) * 1000

        # Network latency (device → server)
        if self.t2_device_request_sent and self.t3_server_request_received:
            deltas["network_device_to_server_ms"] = (self.t3_server_request_received - self.t2_device_request_sent) * 1000

        # Server processing stages
        if self.t3_server_request_received and self.t4_server_decode_complete:
            deltas["server_decode_ms"] = (self.t4_server_decode_complete - self.t3_server_request_received) * 1000

        if self.t4_server_decode_complete and self.t5_server_similarity_hash:
            deltas["server_similarity_hash_ms"] = (self.t5_server_similarity_hash - self.t4_server_decode_complete) * 1000

        if self.t5_server_similarity_hash and self.t6_server_inference_complete:
            deltas["server_inference_ms"] = (self.t6_server_inference_complete - self.t5_server_similarity_hash) * 1000

        if self.t6_server_inference_complete and self.t7_server_storage_complete:
            deltas["server_storage_ms"] = (self.t7_server_storage_complete - self.t6_server_inference_complete) * 1000

        if self.t7_server_storage_complete and self.t8_server_broadcast_complete:
            deltas["server_broadcast_ms"] = (self.t8_server_broadcast_complete - self.t7_server_storage_complete) * 1000

        if self.t8_server_broadcast_complete and self.t9_server_response_sent:
            deltas["server_response_ms"] = (self.t9_server_response_sent - self.t8_server_broadcast_complete) * 1000

        # Total server processing time
        if self.t3_server_request_received and self.t9_server_response_sent:
            deltas["server_total_ms"] = (self.t9_server_response_sent - self.t3_server_request_received) * 1000

        # End-to-end (device capture → server response)
        if self.t0_device_capture and self.t9_server_response_sent:
            deltas["e2e_device_to_response_ms"] = (self.t9_server_response_sent - self.t0_device_capture) * 1000

        return deltas

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        deltas = self.compute_deltas()
        return {
            "record_id": self.record_id,
            "device_id": self.device_id,
            "timestamps": {
                "t0_device_capture": self.t0_device_capture,
                "t1_device_thumbnail": self.t1_device_thumbnail,
                "t2_device_request_sent": self.t2_device_request_sent,
                "t3_server_request_received": self.t3_server_request_received,
                "t4_server_decode_complete": self.t4_server_decode_complete,
                "t5_server_similarity_hash": self.t5_server_similarity_hash,
                "t6_server_inference_complete": self.t6_server_inference_complete,
                "t7_server_storage_complete": self.t7_server_storage_complete,
                "t8_server_broadcast_complete": self.t8_server_broadcast_complete,
                "t9_server_response_sent": self.t9_server_response_sent,
            },
            "deltas_ms": deltas,
            "metadata": {
                "similarity_cache_hit": self.similarity_cache_hit,
                "state": self.state,
                "created_at": self.created_at.isoformat(),
            }
        }


class TimingStats:
    """
    Thread-safe storage and statistics for capture timing data.
    Maintains a circular buffer of the last N captures.
    """

    def __init__(self, max_captures: int = 100):
        self.max_captures = max_captures
        self._captures: deque[CaptureTimings] = deque(maxlen=max_captures)

    def add_timing(self, timing: CaptureTimings) -> None:
        """Add a timing record to the buffer."""
        self._captures.append(timing)
        logger.debug(
            "Timing recorded record=%s device=%s total_stored=%d",
            timing.record_id,
            timing.device_id,
            len(self._captures),
        )

    def get_recent(self, limit: int = 20) -> list[dict[str, Any]]:
        """Get the most recent N timing records."""
        recent = list(self._captures)[-limit:]
        return [t.to_dict() for t in reversed(recent)]

    def compute_statistics(self) -> dict[str, Any]:
        """
        Compute aggregate statistics across all stored captures.
        Returns avg, min, max, p95 for each timing stage.
        """
        if not self._captures:
            return {"message": "No timing data available"}

        # Collect all deltas
        all_deltas: dict[str, list[float]] = {}
        cache_hits = 0
        total = len(self._captures)

        for timing in self._captures:
            deltas = timing.compute_deltas()
            if timing.similarity_cache_hit:
                cache_hits += 1

            for key, value in deltas.items():
                if value is not None:
                    all_deltas.setdefault(key, []).append(value)

        # Compute stats for each stage
        stats: dict[str, dict[str, float]] = {}
        for stage, values in all_deltas.items():
            if not values:
                continue

            sorted_values = sorted(values)
            p95_idx = int(len(sorted_values) * 0.95)

            stats[stage] = {
                "avg_ms": statistics.mean(values),
                "min_ms": min(values),
                "max_ms": max(values),
                "p95_ms": sorted_values[p95_idx] if p95_idx < len(sorted_values) else sorted_values[-1],
                "samples": len(values),
            }

        return {
            "total_captures": total,
            "cache_hit_rate": cache_hits / total if total > 0 else 0,
            "cache_hits": cache_hits,
            "stages": stats,
        }

    def clear(self) -> None:
        """Clear all stored timing data."""
        self._captures.clear()
        logger.info("Timing stats cleared")


# Global instance (initialized when debug mode is enabled)
_timing_stats: TimingStats | None = None


def init_timing_stats(enabled: bool = False, max_captures: int = 100) -> TimingStats | None:
    """Initialize the global timing stats instance if debug mode is enabled."""
    global _timing_stats
    if enabled:
        _timing_stats = TimingStats(max_captures=max_captures)
        logger.info("Timing debug enabled max_captures=%d", max_captures)
    else:
        _timing_stats = None
        logger.info("Timing debug disabled")
    return _timing_stats


def get_timing_stats() -> TimingStats | None:
    """Get the global timing stats instance (None if disabled)."""
    return _timing_stats


def is_timing_enabled() -> bool:
    """Check if timing debug is currently enabled."""
    return _timing_stats is not None
