"""Configuration loader for OK Monitor cloud server.

Loads configuration from JSON file with environment variable overrides.
Replaces the 30+ CLI arguments with a clean configuration file.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class ServerConfig:
    """Server host and port configuration."""
    host: str = "0.0.0.0"
    port: int = 8000


@dataclass
class StorageConfig:
    """Storage paths configuration."""
    datalake_root: str = "/mnt/data/datalake"


@dataclass
class OpenAIConfig:
    """OpenAI classifier configuration."""
    model: str = "gpt-4o-mini"
    base_url: str = "https://api.openai.com/v1"
    timeout: float = 30.0
    api_key_env: str = "OPENAI_API_KEY"


@dataclass
class GeminiConfig:
    """Gemini classifier configuration."""
    model: str = "models/gemini-2.5-flash"
    base_url: str = "https://generativelanguage.googleapis.com/v1beta"
    timeout: float = 30.0
    api_key_env: str = "GEMINI_API_KEY"


@dataclass
class ClassifierConfig:
    """AI classifier configuration."""
    backend: str = "simple"
    primary_backend: str | None = None
    secondary_backend: str | None = None
    openai: OpenAIConfig = None
    gemini: GeminiConfig = None

    def __post_init__(self):
        if self.openai is None or isinstance(self.openai, dict):
            self.openai = OpenAIConfig() if self.openai is None else OpenAIConfig(**self.openai)
        if self.gemini is None or isinstance(self.gemini, dict):
            self.gemini = GeminiConfig() if self.gemini is None else GeminiConfig(**self.gemini)


@dataclass
class DedupeConfig:
    """Deduplication feature configuration."""
    enabled: bool = False
    threshold: int = 3
    keep_every: int = 5


@dataclass
class SimilarityConfig:
    """Similarity detection feature configuration."""
    enabled: bool = False
    threshold: int = 6
    expiry_minutes: float = 60.0
    cache_path: str = "config/similarity_cache.json"


@dataclass
class StreakPruningConfig:
    """Streak-based image pruning configuration."""
    enabled: bool = False
    threshold: int = 10
    keep_every: int = 5


@dataclass
class TimingDebugConfig:
    """Timing debug feature configuration."""
    enabled: bool = False
    max_captures: int = 100


@dataclass
class FeaturesConfig:
    """Feature flags configuration."""
    dedupe: DedupeConfig = None
    similarity: SimilarityConfig = None
    streak_pruning: StreakPruningConfig = None
    timing_debug: TimingDebugConfig = None

    def __post_init__(self):
        if self.dedupe is None or isinstance(self.dedupe, dict):
            self.dedupe = DedupeConfig() if self.dedupe is None else DedupeConfig(**self.dedupe)
        if self.similarity is None or isinstance(self.similarity, dict):
            self.similarity = SimilarityConfig() if self.similarity is None else SimilarityConfig(**self.similarity)
        if self.streak_pruning is None or isinstance(self.streak_pruning, dict):
            self.streak_pruning = StreakPruningConfig() if self.streak_pruning is None else StreakPruningConfig(**self.streak_pruning)
        if self.timing_debug is None or isinstance(self.timing_debug, dict):
            self.timing_debug = TimingDebugConfig() if self.timing_debug is None else TimingDebugConfig(**self.timing_debug)


@dataclass
class PathsConfig:
    """File paths configuration."""
    normal_description: str = "/mnt/data/config/normal_description.txt"
    notification_config: str = "config/notifications.json"
    similarity_cache: str = "config/similarity_cache.json"


@dataclass
class EmailConfig:
    """Email notification configuration."""
    sendgrid_api_key_env: str = "SENDGRID_API_KEY"
    alert_from_email_env: str = "ALERT_FROM_EMAIL"
    alert_environment_label_env: str = "ALERT_ENVIRONMENT_LABEL"


@dataclass
class CloudConfig:
    """Complete cloud server configuration."""
    server: ServerConfig = None
    storage: StorageConfig = None
    classifier: ClassifierConfig = None
    features: FeaturesConfig = None
    paths: PathsConfig = None
    email: EmailConfig = None

    def __post_init__(self):
        if self.server is None or isinstance(self.server, dict):
            self.server = ServerConfig() if self.server is None else ServerConfig(**self.server)
        if self.storage is None or isinstance(self.storage, dict):
            self.storage = StorageConfig() if self.storage is None else StorageConfig(**self.storage)
        if self.classifier is None or isinstance(self.classifier, dict):
            self.classifier = ClassifierConfig() if self.classifier is None else ClassifierConfig(**self.classifier)
        if self.features is None or isinstance(self.features, dict):
            self.features = FeaturesConfig() if self.features is None else FeaturesConfig(**self.features)
        if self.paths is None or isinstance(self.paths, dict):
            self.paths = PathsConfig() if self.paths is None else PathsConfig(**self.paths)
        if self.email is None or isinstance(self.email, dict):
            self.email = EmailConfig() if self.email is None else EmailConfig(**self.email)


def _nested_get(data: dict[str, Any], path: str, default: Any = None) -> Any:
    """Get nested dictionary value using dot notation."""
    keys = path.split(".")
    value = data
    for key in keys:
        if isinstance(value, dict):
            value = value.get(key)
            if value is None:
                return default
        else:
            return default
    return value


def _nested_set(data: dict[str, Any], path: str, value: Any) -> None:
    """Set nested dictionary value using dot notation."""
    keys = path.split(".")
    for key in keys[:-1]:
        if key not in data:
            data[key] = {}
        data = data[key]
    data[keys[-1]] = value


def _dict_to_dataclass(cls, data: dict[str, Any]):
    """Convert dictionary to dataclass recursively."""
    if data is None:
        data = {}

    fieldtypes = {f.name: f.type for f in cls.__dataclass_fields__.values()}
    kwargs = {}

    for field_name, field_type in fieldtypes.items():
        value = data.get(field_name)

        # Handle nested dataclasses
        if hasattr(field_type, "__dataclass_fields__"):
            # Convert dict to dataclass, or use empty dict if None
            kwargs[field_name] = _dict_to_dataclass(field_type, value if value is not None else {})
        else:
            kwargs[field_name] = value

    return cls(**kwargs)


def load_config(config_path: str | Path | None = None) -> CloudConfig:
    """Load configuration from JSON file with environment overrides.

    Args:
        config_path: Path to JSON config file. If None, uses defaults.

    Returns:
        CloudConfig instance with all settings loaded.

    Raises:
        FileNotFoundError: If config file specified but not found.
        json.JSONDecodeError: If config file is invalid JSON.
    """
    # Start with default config
    config_dict: dict[str, Any] = {}

    # Load from JSON file if provided
    if config_path:
        path = Path(config_path)
        if not path.exists():
            raise FileNotFoundError(f"Config file not found: {config_path}")

        with open(path, "r", encoding="utf-8") as f:
            config_dict = json.load(f)

    # Override timing_debug from environment variable if set
    timing_debug_env = os.environ.get("ENABLE_TIMING_DEBUG", "").lower()
    if timing_debug_env == "true":
        _nested_set(config_dict, "features.timing_debug.enabled", True)

    # Convert dict to dataclass
    config = _dict_to_dataclass(CloudConfig, config_dict)

    return config


def create_example_config() -> dict[str, Any]:
    """Create example configuration dictionary for cloud.example.json."""
    return {
        "server": {
            "host": "0.0.0.0",
            "port": 8000
        },
        "storage": {
            "datalake_root": "/mnt/data/datalake"
        },
        "classifier": {
            "backend": "openai",
            "primary_backend": None,
            "secondary_backend": None,
            "openai": {
                "model": "gpt-4o-mini",
                "base_url": "https://api.openai.com/v1",
                "timeout": 30.0,
                "api_key_env": "OPENAI_API_KEY"
            },
            "gemini": {
                "model": "models/gemini-2.5-flash",
                "base_url": "https://generativelanguage.googleapis.com/v1beta",
                "timeout": 30.0,
                "api_key_env": "GEMINI_API_KEY"
            }
        },
        "features": {
            "dedupe": {
                "enabled": False,
                "threshold": 3,
                "keep_every": 5
            },
            "similarity": {
                "enabled": False,
                "threshold": 6,
                "expiry_minutes": 60.0,
                "cache_path": "config/similarity_cache.json"
            },
            "streak_pruning": {
                "enabled": False,
                "threshold": 10,
                "keep_every": 5
            },
            "timing_debug": {
                "enabled": False,
                "max_captures": 100
            }
        },
        "paths": {
            "normal_description": "/mnt/data/config/normal_description.txt",
            "notification_config": "config/notifications.json",
            "similarity_cache": "config/similarity_cache.json"
        },
        "email": {
            "sendgrid_api_key_env": "SENDGRID_API_KEY",
            "alert_from_email_env": "ALERT_FROM_EMAIL",
            "alert_environment_label_env": "ALERT_ENVIRONMENT_LABEL"
        }
    }


if __name__ == "__main__":
    # Generate example config file
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "generate-example":
        example = create_example_config()
        output_path = Path("config/cloud.example.json")
        output_path.parent.mkdir(exist_ok=True)

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(example, f, indent=2)
            f.write("\n")

        print(f"Generated example config: {output_path}")
    else:
        # Test loading
        config = load_config()
        print(f"Server: {config.server.host}:{config.server.port}")
        print(f"Classifier: {config.classifier.backend}")
        print(f"Datalake: {config.storage.datalake_root}")
