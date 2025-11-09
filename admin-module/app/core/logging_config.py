"""
Конфигурация логирования для Admin Module.
Поддерживает JSON и текстовый форматы с обязательными и опциональными полями.
"""

import logging
import sys
from pythonjsonlogger import jsonlogger
from typing import Optional

from app.core.config import settings


class CustomJsonFormatter(jsonlogger.JsonFormatter):
    """
    Кастомный JSON formatter с дополнительными полями.
    Добавляет обязательные и опциональные поля согласно требованиям CLAUDE.md.
    """

    def add_fields(self, log_record, record, message_dict):
        """
        Добавляет обязательные и опциональные поля в JSON лог.

        Обязательные поля:
        - timestamp: ISO 8601 формат с timezone
        - level: Уровень логирования
        - logger: Имя логгера
        - message: Сообщение лога
        - module: Имя модуля
        - function: Имя функции
        - line: Номер строки

        Опциональные поля (добавляются через extra):
        - request_id: ID запроса (для трейсинга)
        - user_id: ID пользователя
        - trace_id: ID trace (для OpenTelemetry)
        - span_id: ID span (для OpenTelemetry)
        """
        super().add_fields(log_record, record, message_dict)

        # Обязательные поля
        if not log_record.get('timestamp'):
            log_record['timestamp'] = record.created

        log_record['level'] = record.levelname
        log_record['logger'] = record.name
        log_record['module'] = record.module
        log_record['function'] = record.funcName
        log_record['line'] = record.lineno

        # Опциональные поля (если переданы через extra)
        # Эти поля будут автоматически добавлены из message_dict если они есть


def setup_logging(
    level: Optional[str] = None,
    format_type: Optional[str] = None,
    log_file: Optional[str] = None
) -> None:
    """
    Настройка логирования для приложения.

    Args:
        level: Уровень логирования (DEBUG, INFO, WARNING, ERROR, CRITICAL).
               По умолчанию берется из settings.logging.level
        format_type: Формат логов ('json' или 'text').
                    По умолчанию берется из settings.logging.format
        log_file: Путь к файлу лога (опционально).
                 По умолчанию берется из settings.logging.log_file

    Raises:
        ValueError: Если указан некорректный уровень или формат логирования
    """
    # Используем настройки по умолчанию из config
    log_level = level or settings.logging.level
    log_format = format_type or settings.logging.format
    log_file_path = log_file or settings.logging.log_file

    # Валидация уровня логирования
    numeric_level = getattr(logging, log_level.upper(), None)
    if not isinstance(numeric_level, int):
        raise ValueError(f'Invalid log level: {log_level}')

    # Валидация формата
    if log_format not in ('json', 'text'):
        raise ValueError(f'Invalid log format: {log_format}. Must be "json" or "text"')

    # Создаем список handlers
    handlers = []

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(numeric_level)

    if log_format == 'json':
        # JSON формат (production)
        # Не используем rename_fields, вместо этого add_fields обработает все поля
        formatter = CustomJsonFormatter(
            '%(message)s',
            timestamp=True
        )
    else:
        # Text формат (development only)
        if not settings.debug:
            # В production режиме text формат запрещен
            raise ValueError(
                'Text log format is only allowed in development mode. '
                'Set APP_DEBUG=true or use LOG_FORMAT=json'
            )
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(module)s:%(funcName)s:%(lineno)d - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )

    console_handler.setFormatter(formatter)
    handlers.append(console_handler)

    # File handler (опционально)
    if log_file_path:
        file_handler = logging.FileHandler(log_file_path, encoding='utf-8')
        file_handler.setLevel(numeric_level)
        file_handler.setFormatter(formatter)
        handlers.append(file_handler)

    # Настройка root logger
    logging.basicConfig(
        level=numeric_level,
        handlers=handlers,
        force=True  # Перезаписать существующую конфигурацию
    )

    # Настройка логирования для uvicorn
    uvicorn_logger = logging.getLogger("uvicorn")
    uvicorn_logger.setLevel(numeric_level)

    uvicorn_access_logger = logging.getLogger("uvicorn.access")
    uvicorn_access_logger.setLevel(numeric_level)

    # Логируем конфигурацию
    logger = logging.getLogger(__name__)
    logger.info(
        "Logging configured",
        extra={
            'log_level': log_level,
            'log_format': log_format,
            'log_file': log_file_path or 'console only',
            'debug_mode': settings.debug
        }
    )


def get_logger(name: str) -> logging.Logger:
    """
    Получить logger с правильной конфигурацией.

    Args:
        name: Имя логгера (обычно __name__)

    Returns:
        logging.Logger: Настроенный logger

    Example:
        >>> logger = get_logger(__name__)
        >>> logger.info("User logged in", extra={'user_id': 123, 'request_id': 'abc-123'})
    """
    return logging.getLogger(name)
