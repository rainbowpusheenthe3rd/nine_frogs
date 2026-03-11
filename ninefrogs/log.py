"""Loguru setup — import this once in main.py before anything else.

All stdlib logging (uvicorn, sqlalchemy, httpx, etc.) is intercepted and
routed through loguru so every log line has the same format:

    2024-01-01 12:00:00.123 | INFO     | research.pipeline:_pipeline:145 - msg
"""
from __future__ import annotations

import logging
import sys

from loguru import logger


class _InterceptHandler(logging.Handler):
    """Forward stdlib logging records to loguru."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = str(record.levelno)

        frame, depth = logging.currentframe(), 2
        while frame and frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back  # type: ignore[assignment]
            depth += 1

        logger.opt(depth=depth, exception=record.exc_info).log(
            level, record.getMessage()
        )


def setup_logging(level: str = "INFO") -> None:
    """Configure loguru and intercept stdlib logging."""
    logger.remove()
    logger.add(
        sys.stderr,
        level=level,
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
            "<level>{level:<8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
            "<level>{message}</level>"
        ),
        colorize=True,
        backtrace=True,
        diagnose=True,
    )

    # Intercept everything from stdlib logging
    logging.basicConfig(handlers=[_InterceptHandler()], level=0, force=True)

    # Quiet down noisy libraries
    for noisy in ("uvicorn.access", "uvicorn.error", "httpcore"):
        logging.getLogger(noisy).setLevel(logging.INFO)
