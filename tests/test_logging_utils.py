from __future__ import annotations

import logging

from cloud.api.logging_utils import StartupLogBufferHandler


def test_startup_buffer_writes_file(tmp_path) -> None:
    handler = StartupLogBufferHandler(output_dir=tmp_path, window_seconds=5.0, capacity=10)
    handler.setFormatter(logging.Formatter("%(levelname)s:%(message)s"))

    test_logger = logging.getLogger("okmonitor.test.startup")
    original_level = test_logger.level
    test_logger.setLevel(logging.INFO)

    root = logging.getLogger()
    original_root_level = root.level
    root.setLevel(logging.DEBUG)
    root.addHandler(handler)
    try:
        test_logger.info("boot sequence")
        test_logger.warning("subsystem ready")
        handler.flush()
    finally:
        root.removeHandler(handler)
        root.setLevel(original_root_level)
        handler.close()
        test_logger.setLevel(original_level)

    files = list(tmp_path.glob("startup_*.log"))
    assert len(files) == 1
    contents = files[0].read_text(encoding="utf-8")
    assert "INFO:boot sequence" in contents
    assert "WARNING:subsystem ready" in contents


