"""
Настройка структурированного логирования для приложения.
Поддерживает JSON и текстовый формат, различные обработчики.
"""
import logging
import sys
from pathlib import Path
from typing import Optional

from pythonjsonlogger import jsonlogger


def setup_logging(
    level: str = "INFO",
    format_type: str = "json",
    output: str = "stdout",
    file_path: Optional[str] = None,
    service_name: str = "admin-module",
) -> None:
    """
    Настраивает логирование для приложения.

    Args:
        level: Уровень логирования (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        format_type: Формат логов (json или text)
        output: Куда выводить логи (stdout или file)
        file_path: Путь к файлу логов (для output=file)
        service_name: Название сервиса для логов
    """
    # Получаем root logger
    logger = logging.getLogger()
    logger.setLevel(getattr(logging, level.upper()))

    # Удаляем существующие handlers
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)

    # Создаем handler в зависимости от output
    if output == "stdout":
        handler = logging.StreamHandler(sys.stdout)
    elif output == "file":
        if not file_path:
            raise ValueError("file_path должен быть указан для output=file")

        # Создаем директорию для логов если не существует
        log_dir = Path(file_path).parent
        log_dir.mkdir(parents=True, exist_ok=True)

        handler = logging.FileHandler(file_path, encoding="utf-8")
    else:
        raise ValueError(f"Неизвестный тип output: {output}")

    # Настраиваем форматтер
    if format_type == "json":
        formatter = jsonlogger.JsonFormatter(
            "%(asctime)s %(levelname)s %(name)s %(message)s",
            rename_fields={
                "asctime": "timestamp",
                "levelname": "level",
                "name": "logger",
            },
        )
        # Добавляем service_name ко всем логам
        old_format = formatter.format

        def format_with_service(record):
            result = old_format(record)
            # Добавляем service_name в JSON
            import json

            log_dict = json.loads(result)
            log_dict["service"] = service_name
            return json.dumps(log_dict)

        formatter.format = format_with_service
    elif format_type == "text":
        formatter = logging.Formatter(
            fmt=f"%(asctime)s - {service_name} - %(name)s - %(levelname)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    else:
        raise ValueError(f"Неизвестный тип формата: {format_type}")

    handler.setFormatter(formatter)
    logger.addHandler(handler)

    # Настраиваем уровни для сторонних библиотек
    logging.getLogger("uvicorn").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy").setLevel(logging.WARNING)

    logger.info(f"Логирование инициализировано: level={level}, format={format_type}, output={output}")


def get_logger(name: str) -> logging.Logger:
    """
    Получает logger для модуля.

    Args:
        name: Имя logger'а (обычно __name__)

    Returns:
        Настроенный logger

    Example:
        >>> logger = get_logger(__name__)
        >>> logger.info("Приложение запущено")
    """
    return logging.getLogger(name)


class AuditLogger:
    """
    Специальный logger для audit событий.
    Логирует критичные действия пользователей и администраторов.
    """

    def __init__(self, service_name: str = "admin-module"):
        self.logger = logging.getLogger(f"{service_name}.audit")
        self.service_name = service_name

    def log_auth_event(
        self,
        event_type: str,
        username: str,
        success: bool,
        ip_address: Optional[str] = None,
        details: Optional[str] = None,
    ) -> None:
        """
        Логирует событие аутентификации.

        Args:
            event_type: Тип события (login, logout, token_refresh, etc.)
            username: Имя пользователя
            success: Успешно ли событие
            ip_address: IP адрес пользователя
            details: Дополнительные детали
        """
        self.logger.info(
            f"AUTH_EVENT: {event_type}",
            extra={
                "event_type": "auth",
                "auth_event": event_type,
                "username": username,
                "success": success,
                "ip_address": ip_address,
                "details": details,
            },
        )

    def log_admin_action(
        self,
        action: str,
        admin_username: str,
        target: Optional[str] = None,
        details: Optional[str] = None,
    ) -> None:
        """
        Логирует административное действие.

        Args:
            action: Тип действия (create_user, delete_user, etc.)
            admin_username: Имя администратора
            target: Цель действия (например, имя пользователя)
            details: Дополнительные детали
        """
        self.logger.info(
            f"ADMIN_ACTION: {action}",
            extra={
                "event_type": "admin",
                "action": action,
                "admin": admin_username,
                "target": target,
                "details": details,
            },
        )

    def log_data_access(
        self,
        resource: str,
        username: str,
        action: str,
        success: bool,
        details: Optional[str] = None,
    ) -> None:
        """
        Логирует доступ к данным.

        Args:
            resource: Ресурс (например, "users", "storage_elements")
            username: Имя пользователя
            action: Действие (read, create, update, delete)
            success: Успешно ли действие
            details: Дополнительные детали
        """
        self.logger.info(
            f"DATA_ACCESS: {resource}",
            extra={
                "event_type": "data_access",
                "resource": resource,
                "username": username,
                "action": action,
                "success": success,
                "details": details,
            },
        )

    def log_security_event(
        self,
        event_type: str,
        severity: str,
        description: str,
        username: Optional[str] = None,
        ip_address: Optional[str] = None,
    ) -> None:
        """
        Логирует событие безопасности.

        Args:
            event_type: Тип события (brute_force, unauthorized_access, etc.)
            severity: Серьезность (low, medium, high, critical)
            description: Описание события
            username: Имя пользователя (если применимо)
            ip_address: IP адрес
        """
        log_func = self.logger.warning if severity in ["high", "critical"] else self.logger.info
        log_func(
            f"SECURITY_EVENT: {event_type}",
            extra={
                "event_type": "security",
                "security_event": event_type,
                "severity": severity,
                "description": description,
                "username": username,
                "ip_address": ip_address,
            },
        )
