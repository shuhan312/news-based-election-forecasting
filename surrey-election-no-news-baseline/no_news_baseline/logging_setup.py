"""Logging for training runs, and the one rule about what may be logged.

Why not print()
---------------
The build script reported progress with ``print``, which has no severity, no
timestamps, and no way to send a record to a file as well as a terminal. The
brief asks for logging and error handling, and a training run that takes
minutes and writes twenty-six files needs a record that survives the terminal
scrollback.

What must never be logged
-------------------------
Predicted or observed vote shares for the primary holdout, at row level.
Progress output is the one part of a run nobody reviews carefully, and the
blinding discipline is only as strong as its weakest channel. Aggregate
holdout metrics are logged, because they are published in ``metrics.json``
anyway; individual 2026 rows are not.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

LOGGER_NAME = "no_news_baseline"

# Timestamped, because "how long did the boosted architecture take" is a
# question that gets asked and cannot be answered afterwards otherwise.
FORMAT = "%(asctime)s %(levelname)-7s %(name)s | %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def get_logger(name: str | None = None) -> logging.Logger:
    """The package logger, or a named child of it."""

    return logging.getLogger(LOGGER_NAME if name is None else f"{LOGGER_NAME}.{name}")


def configure_logging(
    *,
    level: str = "INFO",
    log_file: Path | None = None,
) -> logging.Logger:
    """Send records to stderr, and to ``log_file`` when one is given.

    stderr rather than stdout so that a caller piping the run's own output
    somewhere is not handed the log as well.

    Handlers are replaced rather than added, so calling this twice in one
    process - which the tests do - does not produce doubled records.
    """

    logger = get_logger()
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    logger.propagate = False
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()

    formatter = logging.Formatter(FORMAT, datefmt=DATE_FORMAT)

    stream = logging.StreamHandler(stream=sys.stderr)
    stream.setFormatter(formatter)
    logger.addHandler(stream)

    if log_file is not None:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        # Append rather than truncate: successive runs into the same bundle
        # directory build a history, and a rebuild that overwrote the record
        # of the run before it would destroy the only evidence of what
        # changed between them.
        file_handler = logging.FileHandler(log_file, mode="a", encoding="utf-8")
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger
