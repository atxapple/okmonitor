from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .loopback import LoopbackDigitalIO, TriggerEvent


class DigitalInput(Protocol):
    def wait_for_trigger(self, timeout: float = 1.0) -> TriggerEvent | None:
        ...


@dataclass
class TriggerConfig:
    name: str = "ok-trigger"
    poll_interval: float = 0.1


class Trigger:
    """Stub implementation of ok-trigger."""

    def __init__(self, digital_input: DigitalInput, config: TriggerConfig | None = None) -> None:
        self._input = digital_input
        self._config = config or TriggerConfig()

    def next_event(self, timeout: float = 1.0) -> TriggerEvent | None:
        return self._input.wait_for_trigger(timeout=timeout)


__all__ = ["Trigger", "TriggerConfig", "DigitalInput", "TriggerEvent", "LoopbackDigitalIO"]