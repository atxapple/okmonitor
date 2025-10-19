"""Persistent server configuration management.

This module manages configuration that needs to persist across Railway deployments.
It stores only configuration that is:
- Changed via the UI
- Not already persisted by other modules (email notifications, timestamped files)
- Required to restore server state on startup

Configuration stored:
- Trigger config (enabled, interval_seconds)
- Active normal description filename

Configuration NOT stored here (already persisted elsewhere):
- Email notification settings → config/notifications.json
- Normal description files → config/normal_*.txt (timestamped)
- Similarity cache → config/similarity_cache.json
- UI preferences → config/ui_preferences.json
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class TriggerConfigData:
    """Trigger configuration that persists across deployments."""

    enabled: bool = False
    interval_seconds: float | None = None


@dataclass
class ServerConfig:
    """Server configuration that persists across Railway deployments.

    This stores only the minimal configuration needed to restore server state
    after a deployment. Other configuration is stored in separate files.
    """

    trigger: TriggerConfigData
    active_normal_description_file: str | None = None
    last_updated: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "trigger": asdict(self.trigger),
            "active_normal_description_file": self.active_normal_description_file,
            "last_updated": self.last_updated,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ServerConfig:
        """Create ServerConfig from dictionary."""
        trigger_data = data.get("trigger", {})
        if not isinstance(trigger_data, dict):
            trigger_data = {}

        trigger = TriggerConfigData(
            enabled=bool(trigger_data.get("enabled", False)),
            interval_seconds=_sanitize_interval(trigger_data.get("interval_seconds")),
        )

        active_file = data.get("active_normal_description_file")
        if active_file and not isinstance(active_file, str):
            active_file = None

        last_updated = data.get("last_updated")
        if last_updated and not isinstance(last_updated, str):
            last_updated = None

        return cls(
            trigger=trigger,
            active_normal_description_file=active_file,
            last_updated=last_updated,
        )


def _sanitize_interval(value: Any) -> float | None:
    """Sanitize trigger interval value."""
    if value is None:
        return None
    try:
        interval = float(value)
        if interval < 7.0:  # Minimum interval
            return None
        return interval
    except (TypeError, ValueError):
        return None


def load_server_config(path: Path) -> ServerConfig:
    """Load server configuration from persistent storage.

    Args:
        path: Path to server_config.json file

    Returns:
        ServerConfig with loaded values, or defaults if file doesn't exist
        or is invalid.

    The function gracefully handles:
    - Missing file (returns defaults)
    - Invalid JSON (returns defaults, logs warning)
    - Invalid data structure (returns defaults, logs warning)
    """
    if not path.exists():
        logger.info("No persistent server config found at %s; using defaults", path)
        return ServerConfig(trigger=TriggerConfigData())

    try:
        content = path.read_text(encoding="utf-8")
        data = json.loads(content)
        config = ServerConfig.from_dict(data)
        logger.info(
            "Loaded server config from %s: trigger_enabled=%s interval=%s active_file=%s",
            path,
            config.trigger.enabled,
            config.trigger.interval_seconds,
            config.active_normal_description_file,
        )
        return config
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning(
            "Failed to load server config from %s: %s; using defaults", path, exc
        )
        return ServerConfig(trigger=TriggerConfigData())
    except Exception as exc:  # pragma: no cover - unexpected errors
        logger.error(
            "Unexpected error loading server config from %s: %s; using defaults",
            path,
            exc,
        )
        return ServerConfig(trigger=TriggerConfigData())


def save_server_config(path: Path, config: ServerConfig) -> None:
    """Save server configuration to persistent storage.

    Args:
        path: Path to server_config.json file
        config: ServerConfig to save

    Raises:
        OSError: If file cannot be written

    The function:
    - Creates parent directories if needed
    - Updates last_updated timestamp
    - Writes formatted JSON
    - Logs success/failure
    """
    # Ensure parent directory exists
    path.parent.mkdir(parents=True, exist_ok=True)

    # Update timestamp
    config.last_updated = datetime.now(timezone.utc).isoformat()

    # Serialize and write
    serialized = config.to_dict()
    content = json.dumps(serialized, indent=2, sort_keys=True)
    path.write_text(content, encoding="utf-8")

    logger.info(
        "Saved server config to %s: trigger_enabled=%s interval=%s active_file=%s",
        path,
        config.trigger.enabled,
        config.trigger.interval_seconds,
        config.active_normal_description_file,
    )


def update_trigger_config(
    path: Path, enabled: bool, interval_seconds: float | None
) -> None:
    """Update only trigger configuration in persistent storage.

    This is a convenience function for updating trigger config without
    affecting other configuration values.

    Args:
        path: Path to server_config.json file
        enabled: Whether recurring triggers are enabled
        interval_seconds: Interval in seconds (None if disabled)
    """
    config = load_server_config(path)
    config.trigger.enabled = enabled
    config.trigger.interval_seconds = interval_seconds if enabled else None
    save_server_config(path, config)


def update_active_normal_description(path: Path, filename: str | None) -> None:
    """Update only active normal description filename in persistent storage.

    This is a convenience function for updating the active description file
    without affecting other configuration values.

    Args:
        path: Path to server_config.json file
        filename: Filename of the active normal description (e.g., "normal_20251019_abc123.txt")
                  or None to clear
    """
    config = load_server_config(path)
    config.active_normal_description_file = filename
    save_server_config(path, config)


__all__ = [
    "ServerConfig",
    "TriggerConfigData",
    "load_server_config",
    "save_server_config",
    "update_trigger_config",
    "update_active_normal_description",
]
