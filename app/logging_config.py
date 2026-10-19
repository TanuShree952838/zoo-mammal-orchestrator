"""Trace logging for orchestrator handoffs."""

import logging

LOG_FORMAT = "%(levelname)s %(name)s %(message)s"


def configure_logging() -> None:
    # No-op when uvicorn or pytest has already attached a handler.
    logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
