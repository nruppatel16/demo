"""Structured logging setup (structlog).

Human-readable console output by default; JSON when ``LOG_JSON=true``. Never log
secrets — credentials are read once in the broker/data clients and never passed
to the logger.
"""

from __future__ import annotations

import logging

import structlog


def configure_logging(level: str = "INFO", json_output: bool = False) -> None:
    """Configure structlog + stdlib logging once at process startup."""
    logging.basicConfig(
        format="%(message)s",
        level=getattr(logging, level.upper(), logging.INFO),
    )

    renderer = (
        structlog.processors.JSONRenderer()
        if json_output
        else structlog.dev.ConsoleRenderer()
    )

    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, level.upper(), logging.INFO)
        ),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str = "algotrader") -> structlog.BoundLogger:
    """Return a bound structlog logger."""
    return structlog.get_logger(name)
