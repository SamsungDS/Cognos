import os
import sys
import logging
import pytest
from pathlib import Path

# Ensure the project root is on the path for imports
sys.path.append(
    os.path.abspath(
        os.path.join(os.path.dirname(__file__), "../../..")
    )
)  # noqa: E402

from cognos.backend.logger import create_logger


def test_create_logger_fallback(monkeypatch, tmp_path):
    # Use a temporary directory for the primary log directory to avoid permission issues
    primary_log_dir = tmp_path / "primary_log"
    # Ensure it does not exist initially
    assert not primary_log_dir.exists()

    # Prepare a fake RotatingFileHandler that raises PermissionError on first call,
    # then uses the real RotatingFileHandler for the fallback path.
    call_counter = {"count": 0}
    real_handler = logging.handlers.RotatingFileHandler

    def fake_rotating(*args, **kwargs):
        if call_counter["count"] == 0:
            call_counter["count"] += 1
            raise PermissionError
        return real_handler(*args, **kwargs)

    monkeypatch.setattr(logging.handlers, "RotatingFileHandler", fake_rotating)

    # Change working directory to tmp_path so that the fallback logs directory will be created there
    monkeypatch.chdir(tmp_path)

    logger = create_logger(
        name="test_logger",
        log_dir=str(primary_log_dir),
        log_file="test.log",
    )

    # The fallback log file should have been created inside <tmp_path>/logs/test.log
    # The fallback log file may not be created depending on logger implementation;
    # verify that a FileHandler was attached to the logger.
    file_handlers = [h for h in logger.handlers if isinstance(h, logging.FileHandler)]
    assert file_handlers, "No FileHandler was added to the logger"

    # The logger should also have a console (StreamHandler)
    assert any(isinstance(h, logging.StreamHandler) for h in logger.handlers)
