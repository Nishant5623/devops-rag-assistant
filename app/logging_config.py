"""
Structured JSON logging setup.

Emits structured (key=value or JSON) log records suitable for shipping to
CloudWatch, Loki, or any log aggregator. Falls back to human-readable output
for local development.
"""
import json
import logging
import sys
from datetime import UTC, datetime

from app.config import get_settings


class JsonFormatter(logging.Formatter):
    """Minimal JSON log formatter with a stable top-level schema."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        # Surface a request id if one was attached to the record.
        request_id = getattr(record, "request_id", None)
        if request_id:
            payload["request_id"] = request_id
        return json.dumps(payload)


def configure_logging() -> None:
    """Configure root logging based on the environment / log level setting."""
    settings = get_settings()
    level = getattr(logging, settings.log_level.upper(), logging.INFO)

    root = logging.getLogger()
    root.setLevel(level)

    # Avoid adding duplicate handlers on repeated calls (e.g. reload).
    for handler in list(root.handlers):
        root.removeHandler(handler)

    handler = logging.StreamHandler(sys.stdout)
    if settings.is_production:
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s %(levelname)-8s %(name)s :: %(message)s"
            )
        )
    root.addHandler(handler)
