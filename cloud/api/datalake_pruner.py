"""Datalake pruning service to delete old normal/uncertain full-size images.

This module provides functionality to prune the datalake by deleting full-size
images for normal and uncertain captures older than a specified retention period,
while preserving thumbnails and metadata JSON files. Abnormal captures are never
pruned to ensure important alert data is retained.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class PruneStats:
    """Statistics from a pruning operation."""
    files_scanned: int = 0
    images_deleted: int = 0
    images_preserved: int = 0
    abnormal_preserved: int = 0
    bytes_freed: int = 0
    errors: int = 0


def prune_datalake(
    datalake_root: Path,
    retention_days: int,
    dry_run: bool = False,
) -> PruneStats:
    """Prune old normal/uncertain full-size images from the datalake.

    Args:
        datalake_root: Path to the datalake root directory
        retention_days: Number of days to retain full-size images
        dry_run: If True, don't actually delete files, just report what would be deleted

    Returns:
        PruneStats with statistics about the pruning operation
    """
    if retention_days < 1:
        raise ValueError(f"retention_days must be >= 1, got {retention_days}")

    if not datalake_root.exists():
        logger.warning(f"Datalake root does not exist: {datalake_root}")
        return PruneStats()

    cutoff_date = datetime.now(timezone.utc) - timedelta(days=retention_days)
    stats = PruneStats()

    logger.info(
        f"{'DRY RUN: ' if dry_run else ''}Pruning datalake: root={datalake_root}, "
        f"retention={retention_days} days, cutoff={cutoff_date.isoformat()}"
    )

    # Scan all JSON metadata files
    for json_path in datalake_root.rglob("*.json"):
        stats.files_scanned += 1

        try:
            # Read metadata
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            # Extract classification state and capture time
            classification = data.get("classification", {})
            state = classification.get("state", "unknown")
            captured_at_str = data.get("captured_at")

            if not captured_at_str:
                logger.debug(f"Skipping {json_path}: no captured_at timestamp")
                continue

            # Parse capture timestamp
            captured_at = _parse_datetime(captured_at_str)
            if not captured_at:
                logger.debug(f"Skipping {json_path}: invalid timestamp {captured_at_str}")
                continue

            # Never prune abnormal captures
            if state == "abnormal":
                stats.abnormal_preserved += 1
                logger.debug(f"Preserving abnormal capture: {json_path.stem}")
                continue

            # Check if old enough to prune
            if captured_at >= cutoff_date:
                stats.images_preserved += 1
                logger.debug(f"Preserving recent {state} capture: {json_path.stem}")
                continue

            # Prune normal and uncertain captures
            if state in ["normal", "uncertain"]:
                # Get the full-size image path
                record_id = json_path.stem
                image_path = json_path.parent / f"{record_id}.jpeg"

                if not image_path.exists():
                    logger.debug(f"Image already missing: {image_path}")
                    continue

                # Get file size before deletion
                file_size = image_path.stat().st_size

                # Delete the full-size image
                if dry_run:
                    logger.info(f"[DRY RUN] Would delete {state} image: {image_path} ({file_size:,} bytes)")
                else:
                    image_path.unlink()
                    logger.info(f"Deleted {state} image: {image_path} ({file_size:,} bytes)")

                stats.images_deleted += 1
                stats.bytes_freed += file_size
            else:
                logger.debug(f"Unknown state '{state}', preserving: {json_path.stem}")
                stats.images_preserved += 1

        except Exception as exc:
            logger.error(f"Error processing {json_path}: {exc}")
            stats.errors += 1
            continue

    # Log summary
    logger.info(
        f"{'DRY RUN ' if dry_run else ''}Pruning complete: "
        f"scanned={stats.files_scanned}, deleted={stats.images_deleted}, "
        f"preserved={stats.images_preserved}, abnormal_preserved={stats.abnormal_preserved}, "
        f"freed={stats.bytes_freed:,} bytes ({stats.bytes_freed / 1024 / 1024:.2f} MB), "
        f"errors={stats.errors}"
    )

    return stats


def _parse_datetime(value: str) -> datetime | None:
    """Parse ISO8601 datetime string."""
    try:
        # Handle both with and without timezone
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        # Ensure timezone-aware
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, AttributeError):
        return None


__all__ = ["prune_datalake", "PruneStats"]
