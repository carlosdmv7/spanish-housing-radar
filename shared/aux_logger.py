"""Project logging helpers with colored console output."""

from __future__ import annotations

import logging
import sys
from typing import TextIO

RESET = "\033[0m"
DIM = "\033[2m"
COLORS = {
    logging.DEBUG: "\033[36m",  # cyan
    logging.INFO: "\033[32m",  # green
    logging.WARNING: "\033[33m",  # yellow
    logging.ERROR: "\033[31m",  # red
    logging.CRITICAL: "\033[1;31m",  # bold red
}


class ColorFormatter(logging.Formatter):
    """Formatter that colors only the compact metadata prefix by severity."""

    def __init__(self, use_color: bool = True) -> None:
        super().__init__(datefmt="%Y-%m-%d %H:%M:%S")
        self.use_color = use_color

    def format(self, record: logging.LogRecord) -> str:
        record.message = record.getMessage()
        timestamp = self.formatTime(record, self.datefmt)
        location = f"{record.filename}:{record.lineno}"
        prefix = f"{timestamp} | {record.levelname:<8} | {location}"

        if self.use_color:
            color = DIM if record.levelno == logging.DEBUG else COLORS.get(record.levelno, "")
            if color:
                prefix = f"{color}{prefix}{RESET} "

        formatted = f"{prefix}{record.message}"

        if record.exc_info:
            formatted = f"{formatted}\n{self.formatException(record.exc_info)}"
        if record.stack_info:
            formatted = f"{formatted}\n{self.formatStack(record.stack_info)}"

        return formatted


def configure_logger(
    level: int | str = logging.INFO,
    *,
    stream: TextIO | None = None,
    force: bool = True,
    use_color: bool | None = None,
) -> None:
    """Configure root logging once for the app.

    The root configuration means existing calls like
    ``logging.getLogger(__name__)`` automatically use these colors and show the
    source file plus line number where the log was emitted.
    """

    output = stream or sys.stderr
    should_color = output.isatty() if use_color is None else use_color

    handler = logging.StreamHandler(output)
    handler.setFormatter(ColorFormatter(use_color=should_color))

    logging.basicConfig(level=level, handlers=[handler], force=force)


def get_logger(name: str) -> logging.Logger:
    """Return a named logger for convenience in project modules."""

    return logging.getLogger(name)
