from collections import deque
from dataclasses import dataclass
import time


@dataclass
class TriggerEvent:
    """Represents a single DI trigger event."""

    timestamp: float
    label: str = "manual"


class LoopbackDigitalIO:
    """
    In-memory DI/DO loopback used to exercise the trigger to actuation flow.
    """

    def __init__(self) -> None:
        self._trigger_events: deque[TriggerEvent] = deque()
        self._actuation_log: list[tuple[float, bool]] = []

    def inject_trigger(self, label: str = "manual") -> None:
        """Queue a trigger event that ok-trigger can consume."""
        self._trigger_events.append(TriggerEvent(timestamp=time.time(), label=label))

    def wait_for_trigger(self, timeout: float = 1.0) -> TriggerEvent | None:
        """Block until a trigger is available or the timeout elapses."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self._trigger_events:
                return self._trigger_events.popleft()
            time.sleep(0.01)
        return None

    def actuate(self, state: bool) -> None:
        """Record the requested DO state in the actuation log."""
        self._actuation_log.append((time.time(), state))

    @property
    def actuation_log(self) -> list[tuple[float, bool]]:
        return list(self._actuation_log)


__all__ = ["LoopbackDigitalIO", "TriggerEvent"]
