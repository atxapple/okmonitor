from __future__ import annotations

import logging
import threading
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Optional


class StartupLogBufferHandler(logging.Handler):
    """Capture early startup logs and persist them after a short window."""

    def __init__(
        self,
        output_dir: Path,
        window_seconds: float = 180.0,
        capacity: int = 1000,
    ) -> None:
        super().__init__()
        self._output_dir = output_dir
        self._deadline = time.monotonic() + window_seconds
        self._capacity = max(1, capacity)
        self._buffer: list[str] = []
        self._lock = threading.Lock()
        self._flushed = False
        self._file_path: Optional[Path] = None
        self._timer = threading.Timer(window_seconds, self.flush)
        self._timer.daemon = True
        self._timer.start()
        self._logger = logging.getLogger(__name__)

    @property
    def file_path(self) -> Optional[Path]:
        with self._lock:
            return self._file_path

    def emit(self, record: logging.LogRecord) -> None:
        try:
            message = self.format(record)
        except Exception:
            self.handleError(record)
            return
        path: Optional[Path] = None
        with self._lock:
            if self._flushed:
                return
            self._buffer.append(message)
            if len(self._buffer) >= self._capacity or time.monotonic() >= self._deadline:
                path = self._flush_locked()
        if path is not None:
            self._logger.info("Startup logs written to %s", path)

    def flush(self) -> None:
        with self._lock:
            path = self._flush_locked()
        if path is not None:
            self._logger.info("Startup logs written to %s", path)

    def close(self) -> None:
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None
        try:
            self.flush()
        finally:
            super().close()

    def _flush_locked(self) -> Optional[Path]:
        if self._flushed:
            return None
        self._flushed = True
        if not self._buffer:
            return None
        self._output_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        if self._file_path is None:
            self._file_path = self._output_dir / f"startup_{timestamp}.log"
        contents = "\n".join(self._buffer) + "\n"
        self._buffer.clear()
        self._file_path.write_text(contents, encoding="utf-8")
        return self._file_path


def install_startup_log_buffer(
    output_dir: Path | None = None,
    window_seconds: float = 180.0,
    capacity: int = 2000,
    formatter: logging.Formatter | None = None,
) -> StartupLogBufferHandler:
    handler = StartupLogBufferHandler(
        output_dir=output_dir or Path("debug_captures/startup_logs"),
        window_seconds=window_seconds,
        capacity=capacity,
    )
    handler.setLevel(logging.DEBUG)
    handler.setFormatter(
        formatter
        or logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    )
    logging.getLogger().addHandler(handler)
    logging.getLogger(__name__).info(
        "Startup log buffering enabled; keeping %.0f seconds of logs", window_seconds
    )
    return handler


__all__ = ["StartupLogBufferHandler", "install_startup_log_buffer"]

