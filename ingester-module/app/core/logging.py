"""
Ingester Module - Logging Configuration.

JSON и text форматирование с поддержкой structured logging.
"""

import logging
import sys
from pathlib import Path
from typing import Optional

from pythonjsonlogger.json import JsonFormatter

from app.core.config import settings, LogFormat


class CustomJsonFormatter(JsonFormatter):
    """
    Кастомный JSON formatter с дополнительными полями.
    """

    def add_fields(self, log_record, record, message_dict):
        """Добавляет дополнительные поля в JSON лог."""
        super().add_fields(log_record, record, message_dict)

        # Добавляем стандартные поля
        log_record['timestamp'] = self.formatTime(record, self.datefmt)
        log_record['level'] = record.levelname
        log_record['logger'] = record.name
        log_record['module'] = record.module
        log_record['function'] = record.funcName
        log_record['line'] = record.lineno

        # Добавляем application context
        log_record['app_name'] = settings.app.name
        log_record['app_version'] = settings.app.version


def setup_logging(
    level: Optional[str] = None,
    log_format: Optional[str] = None,
    log_file: Optional[Path] = None
) -> None:
    """
    Настройка логирования для приложения.

    Args:
        level: Уровень логирования (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_format: Формат логов (json, text)
        log_file: Путь к файлу логов (опционально)
    """
    # Используем настройки из config если не переданы параметры
    log_level = level or settings.logging.level.value
    format_type = log_format or settings.logging.format.value
    file_path = log_file or settings.logging.file

    # Настройка корневого логгера
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # Удаляем существующие handlers
    root_logger.handlers.clear()

    # Создаем handler для консоли
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)

    # Выбор formatter'а
    if format_type == LogFormat.JSON.value:
        # JSON формат для production
        formatter = CustomJsonFormatter(
            fmt='%(timestamp)s %(level)s %(name)s %(message)s',
            datefmt='%Y-%m-%dT%H:%M:%S'
        )
    else:
        # Text формат для development
        formatter = logging.Formatter(
            fmt='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )

    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # Опционально добавляем file handler
    if file_path:
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(file_path, encoding='utf-8')
        file_handler.setLevel(log_level)
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)

    # Настройка уровней логирования для библиотек
    logging.getLogger("uvicorn").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("fastapi").setLevel(logging.WARNING)

    # Логируем успешную инициализацию
    logger = logging.getLogger(__name__)
    logger.info(
        "Logging configured",
        extra={
            "log_level": log_level,
            "log_format": format_type,
            "log_file": str(file_path) if file_path else None
        }
    )


def get_logger(name: str) -> logging.Logger:
    """
    Получить logger с заданным именем.

    Args:
        name: Имя логгера (обычно __name__ модуля)

    Returns:
        Настроенный logger instance
    """
    return logging.getLogger(name)
