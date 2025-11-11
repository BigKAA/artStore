"""
Система логирования для Storage Element.

Поддержка:
- JSON формат для production (обязательно)
- Text формат для development
- Structured logging с контекстом
- Integration с OpenTelemetry для distributed tracing
"""

import logging
import sys
from pathlib import Path
from typing import Optional

from pythonjsonlogger import jsonlogger

from app.core.config import settings, LogFormat


class CustomJsonFormatter(jsonlogger.JsonFormatter):
    """
    Кастомный JSON formatter с дополнительными полями.

    Добавляет:
    - module: имя модуля
    - function: имя функции
    - line: номер строки
    - trace_id: для distributed tracing (опционально)
    """

    def add_fields(self, log_record, record, message_dict):
        """Добавление кастомных полей в JSON лог"""
        super().add_fields(log_record, record, message_dict)

        # Обязательные поля
        log_record["timestamp"] = record.created
        log_record["level"] = record.levelname
        log_record["logger"] = record.name
        log_record["module"] = record.module
        log_record["function"] = record.funcName
        log_record["line"] = record.lineno

        # Опциональные поля для OpenTelemetry
        if hasattr(record, "trace_id"):
            log_record["trace_id"] = record.trace_id
        if hasattr(record, "span_id"):
            log_record["span_id"] = record.span_id
        if hasattr(record, "request_id"):
            log_record["request_id"] = record.request_id
        if hasattr(record, "user_id"):
            log_record["user_id"] = record.user_id


def setup_logging(
    log_level: Optional[str] = None,
    log_format: Optional[LogFormat] = None,
    log_file: Optional[Path] = None
) -> None:
    """
    Настройка глобальной системы логирования.

    Args:
        log_level: Уровень логирования (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_format: Формат логов (json или text)
        log_file: Путь к файлу для логов (опционально)

    Returns:
        None

    Примеры:
        >>> setup_logging("INFO", LogFormat.JSON)  # Production
        >>> setup_logging("DEBUG", LogFormat.TEXT)  # Development
    """
    # Использование настроек из config если не переданы параметры
    level = log_level or settings.logging.level
    format_type = log_format or settings.logging.format
    file_path = log_file or settings.logging.file_path

    # Конфигурация root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # Очистка существующих handlers
    root_logger.handlers.clear()

    # Создание handler для console (stdout)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)

    # Выбор formatter в зависимости от формата
    if format_type == LogFormat.JSON:
        # JSON formatter для production
        formatter = CustomJsonFormatter(
            "%(timestamp)s %(level)s %(logger)s %(module)s %(function)s %(line)d %(message)s"
        )
    else:
        # Text formatter для development
        formatter = logging.Formatter(
            fmt="%(asctime)s - %(name)s - %(levelname)s - %(module)s:%(funcName)s:%(lineno)d - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )

    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # Добавление file handler если указан путь
    if file_path:
        # Создание директории для логов если не существует
        file_path.parent.mkdir(parents=True, exist_ok=True)

        # Rotating file handler
        from logging.handlers import RotatingFileHandler

        file_handler = RotatingFileHandler(
            filename=file_path,
            maxBytes=settings.logging.max_bytes,
            backupCount=settings.logging.backup_count,
            encoding="utf-8"
        )
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)

    # Настройка логирования для сторонних библиотек
    logging.getLogger("uvicorn").setLevel(logging.INFO)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    logging.getLogger("asyncpg").setLevel(logging.WARNING)

    # Логирование старта системы
    logger = logging.getLogger(__name__)
    logger.info(
        "Logging system initialized",
        extra={
            "log_level": level,
            "log_format": format_type.value,
            "log_file": str(file_path) if file_path else None
        }
    )


def get_logger(name: str) -> logging.Logger:
    """
    Получение настроенного logger для модуля.

    Args:
        name: Имя logger (обычно __name__)

    Returns:
        logging.Logger: Настроенный logger

    Примеры:
        >>> logger = get_logger(__name__)
        >>> logger.info("File uploaded", extra={"file_id": "123", "size": 1024})
    """
    return logging.getLogger(name)


# Инициализация логирования при импорте модуля
setup_logging()
