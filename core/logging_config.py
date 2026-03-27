from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Union


DEFAULT_FORMAT = "%(levelname)s %(asctime)s.%(msecs)03d %(name)s: %(message)s"
DEFAULT_DATEFMT = "%Y-%m-%d %H:%M:%S"
DEFAULT_MAX_BYTES = 5 * 1024 * 1024
DEFAULT_BACKUP_COUNT = 3


def _coerce_level(level: Union[str, int]) -> int:
    if isinstance(level, int):
        return level
    maybe_level = logging.getLevelName(level.upper())
    if isinstance(maybe_level, int):
        return maybe_level
    return logging.INFO


def setup_logging(
    process_name: str,
    level: Union[str, int] = "INFO",
    logs_root: Union[str, Path, None] = None,
) -> logging.Logger:
    """
    Configure process-wide logging with tiered rotating files under logs/<process_name>.

    debug.log receives DEBUG and above.
    important.log receives WARNING and above.
    """
    root_logger = logging.getLogger()
    configured_level = _coerce_level(level)
    root_logger.setLevel(configured_level)

    # Reset handlers so repeated setup calls do not duplicate output.
    for handler in list(root_logger.handlers):
        root_logger.removeHandler(handler)
        handler.close()

    root_path = Path(logs_root) if logs_root is not None else Path.cwd() / "logs"
    process_dir = root_path / process_name
    process_dir.mkdir(parents=True, exist_ok=True)

    formatter = logging.Formatter(DEFAULT_FORMAT, datefmt=DEFAULT_DATEFMT)

    debug_handler = RotatingFileHandler(
        filename=str(process_dir / "debug.log"),
        mode="a",
        maxBytes=DEFAULT_MAX_BYTES,
        backupCount=DEFAULT_BACKUP_COUNT,
        encoding="utf-8",
    )
    debug_handler.setLevel(logging.DEBUG)
    debug_handler.setFormatter(formatter)

    important_handler = RotatingFileHandler(
        filename=str(process_dir / "important.log"),
        mode="a",
        maxBytes=DEFAULT_MAX_BYTES,
        backupCount=DEFAULT_BACKUP_COUNT,
        encoding="utf-8",
    )
    important_handler.setLevel(logging.WARNING)
    important_handler.setFormatter(formatter)

    root_logger.addHandler(debug_handler)
    root_logger.addHandler(important_handler)

    return logging.getLogger(process_name)


def get_logger(name: str) -> logging.Logger:
    """Thin wrapper for module-level logger retrieval."""
    return logging.getLogger(name)
