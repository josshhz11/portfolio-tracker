"""Logging configuration for the portfolio tracker."""

import logging
import sys
from typing import Optional

from src.config import LOG_LEVEL


def setup_logging(
    level: Optional[str] = None,
    fmt: str = "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt: str = "%Y-%m-%d %H:%M:%S",
) -> None:
    """Configure root logger with a sensible default format.

    Args:
        level: Logging level string (e.g. "INFO", "DEBUG"). Defaults to the
               value from config.
        fmt:   Log message format string.
        datefmt: Date/time format string.
    """
    log_level = getattr(logging, (level or LOG_LEVEL).upper(), logging.INFO)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(fmt=fmt, datefmt=datefmt))
    root = logging.getLogger()
    root.setLevel(log_level)
    # Avoid adding duplicate handlers when called multiple times (e.g. tests)
    if not root.handlers:
        root.addHandler(handler)
    else:
        root.handlers[0] = handler


def get_logger(name: str) -> logging.Logger:
    """Return a named logger.

    Args:
        name: Logger name, typically ``__name__`` of the calling module.

    Returns:
        A :class:`logging.Logger` instance.
    """
    return logging.getLogger(name)
