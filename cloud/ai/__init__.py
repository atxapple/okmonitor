from __future__ import annotations

from .types import Classification, Classifier

__all__ = [
    "Classification",
    "Classifier",
    "SimpleThresholdModel",
    "OpenAIImageClassifier",
    "GeminiImageClassifier",
    "ConsensusClassifier",
]


def __getattr__(name: str):
    if name == "SimpleThresholdModel":
        from .simple import SimpleThresholdModel

        return SimpleThresholdModel
    if name == "OpenAIImageClassifier":
        from .openai_client import OpenAIImageClassifier

        return OpenAIImageClassifier
    if name == "GeminiImageClassifier":
        from .gemini_client import GeminiImageClassifier

        return GeminiImageClassifier
    if name == "ConsensusClassifier":
        from .consensus import ConsensusClassifier

        return ConsensusClassifier
    raise AttributeError(f"module 'cloud.ai' has no attribute {name!r}")
