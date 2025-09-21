from __future__ import annotations

from .types import Classification, Classifier

__all__ = [
    "Classification",
    "Classifier",
    "SimpleThresholdModel",
    "OpenAIImageClassifier",
]


def __getattr__(name: str):
    if name == "SimpleThresholdModel":
        from .simple import SimpleThresholdModel

        return SimpleThresholdModel
    if name == "OpenAIImageClassifier":
        from .openai_client import OpenAIImageClassifier

        return OpenAIImageClassifier
    raise AttributeError(f"module 'cloud.ai' has no attribute {name!r}")
