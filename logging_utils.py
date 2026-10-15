"""Structured JSON logging helpers."""

import json
import logging
from datetime import datetime, timezone
from typing import Any


_STANDARD = {
    "name", "msg", "args", "levelname", "levelno", "pathname", "filename",
    "module", "exc_info", "exc_text", "stack_info", "lineno", "funcName",
    "created", "msecs", "relativeCreated", "thread", "threadName",
    "processName", "process", "taskName",
}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        data: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, timezone.utc).isoformat(),
            "level": record.levelname,
            "event": record.getMessage(),
        }
        data.update(
            (key, value)
            for key, value in record.__dict__.items()
            if key not in _STANDARD and not key.startswith("_")
        )
        if record.exc_info:
            data["exception"] = self.formatException(record.exc_info)
        return json.dumps(data, ensure_ascii=False, default=str)


def configure_logging(level: str) -> logging.Logger:
    logger = logging.getLogger("plotpulse")
    logger.handlers.clear()
    logger.setLevel(level.upper())
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    logger.addHandler(handler)
    logger.propagate = False
    return logger


def log_event(logger: logging.Logger, level: int, event: str, **fields: Any) -> None:
    exc_info = bool(fields.pop("exc_info", False))
    logger.log(level, event, extra=fields, exc_info=exc_info)
