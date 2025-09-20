from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .loopback import LoopbackDigitalIO


class DigitalOutput(Protocol):
    def actuate(self, state: bool) -> None:
        ...


@dataclass
class ActuatorConfig:
    name: str = "ok-actuator"


class Actuator:
    """Stub ok-actuator that records the last requested DO state."""

    def __init__(self, digital_output: DigitalOutput, config: ActuatorConfig | None = None) -> None:
        self._output = digital_output
        self._config = config or ActuatorConfig()
        self._last_state: bool | None = None

    def set_state(self, state: bool) -> None:
        self._output.actuate(state)
        self._last_state = state

    @property
    def last_state(self) -> bool | None:
        return self._last_state


__all__ = ["Actuator", "ActuatorConfig", "DigitalOutput", "LoopbackDigitalIO"]