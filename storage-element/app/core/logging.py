"""
Structured logging для Storage Element.

Поддерживает JSON и text форматы с контекстными полями.
"""

import logging
import sys
import json
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from pathlib import Path


class JSONFormatter(logging.Formatter):
    """
    JSON formatter для structured logging.

    Каждое log сообщение форматируется как JSON объект с полями:
    - timestamp: ISO 8601 timestamp
    - level: log level (INFO, ERROR, etc.)
    - logger: logger name
    - message: log message
    - context: additional context fields
    """

    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON."""
        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Добавляем exception info если есть
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)

        # Добавляем дополнительные поля из extra
        for key, value in record.__dict__.items():
            if key not in [
                "name",
                "msg",
                "args",
                "created",
                "filename",
                "funcName",
                "levelname",
                "levelno",
                "lineno",
                "module",
                "msecs",
                "message",
                "pathname",
                "process",
                "processName",
                "relativeCreated",
                "thread",
                "threadName",
                "exc_info",
                "exc_text",
                "stack_info",
            ]:
                log_entry[key] = value

        return json.dumps(log_entry, ensure_ascii=False)


class TextFormatter(logging.Formatter):
    """
    Text formatter для human-readable logging.

    Format: [TIMESTAMP] LEVEL - LOGGER - MESSAGE
    """

    def __init__(self):
        super().__init__(
            fmt="[%(asctime)s] %(levelname)-8s - %(name)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )


class StructuredLogger:
    """
    Structured logger wrapper с удобными методами для контекстного логирования.

    Examples:
        >>> logger = StructuredLogger("storage-element")
        >>> logger.info("File uploaded", file_id="abc123", size=1024)
        >>> logger.error("Upload failed", file_id="abc123", error="Disk full")
    """

    def __init__(self, name: str, log_level: str = "INFO", log_format: str = "json"):
        """
        Initialize structured logger.

        Args:
            name: Logger name
            log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
            log_format: Log format (json or text)
        """
        self.logger = logging.getLogger(name)
        self.logger.setLevel(getattr(logging, log_level.upper()))

        # Remove existing handlers
        self.logger.handlers.clear()

        # Create console handler
        handler = logging.StreamHandler(sys.stdout)

        # Set formatter
        if log_format == "json":
            formatter = JSONFormatter()
        else:
            formatter = TextFormatter()

        handler.setFormatter(formatter)
        self.logger.addHandler(handler)

    def debug(self, message: str, **kwargs):
        """Log debug message with context."""
        self.logger.debug(message, extra=kwargs)

    def info(self, message: str, **kwargs):
        """Log info message with context."""
        self.logger.info(message, extra=kwargs)

    def warning(self, message: str, **kwargs):
        """Log warning message with context."""
        self.logger.warning(message, extra=kwargs)

    def error(self, message: str, **kwargs):
        """Log error message with context."""
        self.logger.error(message, extra=kwargs)

    def critical(self, message: str, **kwargs):
        """Log critical message with context."""
        self.logger.critical(message, extra=kwargs)

    def exception(self, message: str, **kwargs):
        """Log exception with traceback and context."""
        self.logger.exception(message, extra=kwargs)


# Global logger instance
_logger: Optional[StructuredLogger] = None


def get_logger() -> StructuredLogger:
    """
    Get global logger instance (singleton pattern).

    Returns:
        StructuredLogger: Application logger
    """
    global _logger
    if _logger is None:
        from app.core.config import get_config

        config = get_config()
        _logger = StructuredLogger(
            name="storage-element",
            log_level=config.log_level,
            log_format=config.log_format
        )
    return _logger


def configure_logging(log_level: str = "INFO", log_format: str = "json") -> StructuredLogger:
    """
    Configure global logger.

    Args:
        log_level: Logging level
        log_format: Log format (json or text)

    Returns:
        StructuredLogger: Configured logger
    """
    global _logger
    _logger = StructuredLogger(
        name="storage-element",
        log_level=log_level,
        log_format=log_format
    )
    return _logger
