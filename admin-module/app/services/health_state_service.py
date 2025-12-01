"""
Сервис хранения кешированного состояния health checks.

Используется для асинхронной архитектуры readiness probe:
- Background job периодически проверяет состояние БД и Redis
- Результат сохраняется в этом сервисе
- /health/ready endpoint читает из кеша мгновенно (без I/O операций)

Thread-safe для использования из APScheduler background jobs.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List
import threading
import logging

logger = logging.getLogger(__name__)


@dataclass
class DatabaseHealth:
    """Состояние подключения к базе данных."""
    ok: bool = False
    error: Optional[str] = None
    missing_tables: List[str] = field(default_factory=list)


@dataclass
class RedisHealth:
    """Состояние подключения к Redis."""
    ok: bool = False
    error: Optional[str] = None


@dataclass
class HealthState:
    """
    Полное состояние readiness для приложения.

    Attributes:
        database: Состояние PostgreSQL (критичная зависимость)
        redis: Состояние Redis (опциональная зависимость)
        last_check: Время последней проверки
        is_ready: Готово ли приложение принимать трафик
        reason: Причина неготовности (если is_ready=False)
        warnings: Предупреждения (например, Redis недоступен)
    """
    database: DatabaseHealth = field(default_factory=DatabaseHealth)
    redis: RedisHealth = field(default_factory=RedisHealth)
    last_check: Optional[datetime] = None
    is_ready: bool = False
    reason: Optional[str] = None
    warnings: List[str] = field(default_factory=list)


class HealthStateService:
    """
    Singleton сервис для хранения кешированного состояния health checks.

    Thread-safe для использования из APScheduler background jobs.
    Background job вызывает update_state(), endpoint вызывает get_state().

    Example:
        # В background job (scheduler.py):
        state = HealthState(database=DatabaseHealth(ok=True), ...)
        health_state_service.update_state(state)

        # В endpoint (health.py):
        state = health_state_service.get_state()
        return {"status": "ready" if state.is_ready else "not_ready"}
    """
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        """Singleton pattern с double-checked locking."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._state = HealthState()
                    cls._instance._state_lock = threading.Lock()
        return cls._instance

    def update_state(self, state: HealthState) -> None:
        """
        Обновить состояние (вызывается из background job).

        Args:
            state: Новое состояние health checks
        """
        with self._state_lock:
            self._state = state
            logger.debug(
                f"Health state updated: is_ready={state.is_ready}, "
                f"db_ok={state.database.ok}, redis_ok={state.redis.ok}"
            )

    def get_state(self) -> HealthState:
        """
        Получить текущее состояние (вызывается из endpoint).

        Returns:
            HealthState: Текущее кешированное состояние
        """
        with self._state_lock:
            return self._state

    def is_ready(self) -> bool:
        """
        Быстрая проверка готовности без копирования полного состояния.

        Returns:
            bool: True если приложение готово принимать трафик
        """
        with self._state_lock:
            return self._state.is_ready


# Глобальный экземпляр сервиса
health_state_service = HealthStateService()
