"""
Сервис периодической публикации health status в Redis registry.

Публикует статус Storage Element каждые N секунд (по умолчанию 30):
- Capacity информация (total, used, free, percent)
- Adaptive capacity status (OK, WARNING, CRITICAL, FULL)
- Endpoint для доступа
- Priority для Sequential Fill алгоритма

Redis Schema:
- storage:elements:{se_id} - Hash с метаданными SE
- storage:{mode}:by_priority - Sorted Set для выбора SE
"""

import asyncio
import os
from datetime import datetime, timezone
from typing import Optional

from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core.config import settings
from app.core.logging import get_logger
from app.core.capacity_calculator import (
    CapacityStatus,
    calculate_adaptive_threshold,
    get_capacity_status,
    format_capacity_info,
)
from app.core.redis import redis_circuit_breaker

# Sprint 14: Prometheus metrics для capacity monitoring
from app.core.capacity_metrics import (
    update_capacity_metrics,
    record_redis_publish,
    storage_element_info,
)

logger = get_logger(__name__)


class HealthReporter:
    """
    Периодический reporter статуса SE в Redis.

    Особенности:
    - Публикует статус каждые health_report_interval секунд
    - Устанавливает TTL на Redis ключи (interval * ttl_multiplier)
    - При FULL статусе удаляет SE из sorted sets (не выбирается для записи)
    - При shutdown корректно удаляет SE из registry
    """

    def __init__(self, redis_client: Redis):
        """
        Инициализация HealthReporter.

        Args:
            redis_client: Async Redis клиент
        """
        self.redis = redis_client

        # Конфигурация из settings
        self.se_id = settings.storage.element_id
        self.mode = settings.app.mode.value  # rw, edit, ro, ar
        self.priority = settings.storage.priority
        self.endpoint = settings.storage.external_endpoint
        self.interval = settings.storage.health_report_interval
        self.ttl = settings.storage.health_report_ttl

        # Состояние reporter
        self._running = False
        self._task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        """
        Запустить периодическую публикацию статуса.

        Создаёт background task для reporting loop.
        """
        if self._running:
            logger.warning("HealthReporter already running")
            return

        self._running = True
        self._task = asyncio.create_task(self._reporting_loop())

        # Sprint 14: Инициализация Info metric с данными о SE
        storage_element_info.info({
            'storage_element_id': self.se_id,
            'mode': self.mode,
            'priority': str(self.priority),
            'version': settings.app.version,
        })

        logger.info(
            "HealthReporter started",
            extra={
                "se_id": self.se_id,
                "mode": self.mode,
                "interval": self.interval,
                "ttl": self.ttl,
            }
        )

    async def stop(self) -> None:
        """
        Остановить reporting и удалить SE из registry.

        Вызывается при shutdown приложения.
        """
        self._running = False

        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

        # Удаляем SE из registry при graceful shutdown
        await self._remove_from_registry()

        logger.info(f"HealthReporter stopped for SE {self.se_id}")

    async def _reporting_loop(self) -> None:
        """
        Основной цикл публикации статуса.

        Выполняет report каждые interval секунд.
        """
        while self._running:
            try:
                await self._report_status()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(
                    f"Health report failed: {e}",
                    extra={"se_id": self.se_id, "error": str(e)}
                )

            # Ждём до следующего report
            await asyncio.sleep(self.interval)

    async def _report_status(self) -> None:
        """
        Публикация текущего статуса в Redis.

        Обновляет:
        1. Hash с метаданными SE
        2. Sorted Set для приоритетного выбора (если writable mode)
        3. Sprint 14: Prometheus metrics для capacity monitoring
        """
        import time

        # Проверяем circuit breaker
        if redis_circuit_breaker.is_open:
            logger.debug("Redis circuit breaker open, skipping report")
            return

        try:
            # Получаем статистику хранилища
            storage_stats = await self._get_storage_stats()

            # Рассчитываем адаптивные пороги
            thresholds = calculate_adaptive_threshold(
                storage_stats["total"],
                self.mode
            )

            # Определяем статус ёмкости
            capacity_status = get_capacity_status(
                storage_stats["used"],
                storage_stats["total"],
                thresholds
            )

            # Подготавливаем данные для Redis
            now = datetime.now(timezone.utc).isoformat()
            se_data = {
                "id": self.se_id,
                "mode": self.mode,
                "capacity_total": str(storage_stats["total"]),
                "capacity_used": str(storage_stats["used"]),
                "capacity_free": str(storage_stats["free"]),
                "capacity_percent": f"{storage_stats['percent']:.2f}",
                "endpoint": self.endpoint,
                "priority": str(self.priority),
                "last_updated": now,
                "health_status": "healthy",
                "capacity_status": capacity_status.value,
            }

            # Добавляем информацию о порогах (если есть)
            if thresholds:
                se_data["threshold_warning"] = f"{thresholds['warning_threshold']:.2f}"
                se_data["threshold_critical"] = f"{thresholds['critical_threshold']:.2f}"
                se_data["threshold_full"] = f"{thresholds['full_threshold']:.2f}"

            # Sprint 14: Обновляем Prometheus metrics
            update_capacity_metrics(
                element_id=self.se_id,
                mode=self.mode,
                total_bytes=storage_stats["total"],
                used_bytes=storage_stats["used"],
                free_bytes=storage_stats["free"],
                percent_used=storage_stats["percent"],
                status=capacity_status.value,
                health="healthy",
                warning_threshold=thresholds["warning_threshold"] if thresholds else None,
                critical_threshold=thresholds["critical_threshold"] if thresholds else None,
                full_threshold=thresholds["full_threshold"] if thresholds else None,
            )

            # Публикуем в Redis через pipeline с замером времени
            start_time = time.monotonic()
            await self._publish_to_redis(se_data, capacity_status)
            publish_duration = time.monotonic() - start_time

            # Sprint 14: Записываем Redis publish metrics
            record_redis_publish(
                element_id=self.se_id,
                status="success",
                duration_seconds=publish_duration
            )

            # Успешный запрос - сбрасываем circuit breaker
            redis_circuit_breaker.record_success()

            # Логируем статус
            self._log_status(storage_stats, capacity_status, thresholds)

        except RedisError as e:
            redis_circuit_breaker.record_failure()

            # Sprint 14: Записываем неудачную публикацию
            record_redis_publish(
                element_id=self.se_id,
                status="failure"
            )

            raise

    async def _publish_to_redis(
        self,
        se_data: dict,
        capacity_status: CapacityStatus
    ) -> None:
        """
        Публикация данных в Redis.

        Args:
            se_data: Метаданные SE для Hash
            capacity_status: Текущий статус ёмкости
        """
        hash_key = f"storage:elements:{self.se_id}"

        # Используем pipeline для атомарности
        pipe = self.redis.pipeline()

        # 1. Обновляем Hash с метаданными
        pipe.hset(hash_key, mapping=se_data)
        pipe.expire(hash_key, self.ttl)

        # 2. Обновляем Sorted Set для приоритетного выбора
        if self.mode in ("rw", "edit"):
            sorted_set_key = f"storage:{self.mode}:by_priority"

            if capacity_status != CapacityStatus.FULL:
                # SE доступен для записи - добавляем в sorted set
                pipe.zadd(sorted_set_key, {self.se_id: self.priority})
            else:
                # SE полный - удаляем из sorted sets
                pipe.zrem(sorted_set_key, self.se_id)
        else:
            # RO/AR режимы - удаляем из всех sorted sets
            pipe.zrem("storage:rw:by_priority", self.se_id)
            pipe.zrem("storage:edit:by_priority", self.se_id)

        await pipe.execute()

    async def _get_storage_stats(self) -> dict:
        """
        Получение статистики хранилища.

        Returns:
            dict: {total, used, free, percent} в байтах
        """
        if settings.storage.type.value == "local":
            return await self._get_local_stats()
        else:
            return await self._get_s3_stats()

    async def _get_local_stats(self) -> dict:
        """
        Получение статистики локальной файловой системы.

        Returns:
            dict: Статистика диска
        """
        storage_path = str(settings.storage.local_storage_path)

        # Создаём директорию если не существует
        os.makedirs(storage_path, exist_ok=True)

        # Получаем статистику файловой системы
        stat = os.statvfs(storage_path)

        total = stat.f_blocks * stat.f_frsize
        free = stat.f_bavail * stat.f_frsize
        used = total - free
        percent = (used / total * 100) if total > 0 else 0.0

        return {
            "total": total,
            "used": used,
            "free": free,
            "percent": percent,
        }

    async def _get_s3_stats(self) -> dict:
        """
        Получение статистики S3 хранилища.

        Для S3 используем настроенный лимит max_size_gb как total,
        и отслеживаем usage через метаданные файлов в БД.

        Returns:
            dict: Оценочная статистика S3
        """
        # Для S3 total = настроенный лимит
        total = settings.storage.max_size_bytes

        # TODO: В будущем получать actual usage из БД или S3 API
        # Пока используем placeholder
        # Это будет реализовано в Sprint 15 через tracking в БД
        used = 0
        free = total
        percent = 0.0

        return {
            "total": total,
            "used": used,
            "free": free,
            "percent": percent,
        }

    async def _remove_from_registry(self) -> None:
        """
        Удаление SE из Redis registry при shutdown.
        """
        try:
            pipe = self.redis.pipeline()
            pipe.delete(f"storage:elements:{self.se_id}")
            pipe.zrem("storage:rw:by_priority", self.se_id)
            pipe.zrem("storage:edit:by_priority", self.se_id)
            await pipe.execute()

            logger.info(
                f"Removed SE {self.se_id} from Redis registry",
                extra={"se_id": self.se_id}
            )
        except RedisError as e:
            logger.error(
                f"Failed to remove SE from registry: {e}",
                extra={"se_id": self.se_id, "error": str(e)}
            )

    def _log_status(
        self,
        stats: dict,
        status: CapacityStatus,
        thresholds: Optional[dict]
    ) -> None:
        """
        Логирование статуса с appropriate severity.

        Args:
            stats: Статистика хранилища
            status: Текущий статус ёмкости
            thresholds: Адаптивные пороги
        """
        log_data = {
            "event": "storage_capacity_report",
            "se_id": self.se_id,
            "mode": self.mode,
            "capacity": {
                "total_gb": round(stats["total"] / (1024 ** 3), 2),
                "used_gb": round(stats["used"] / (1024 ** 3), 2),
                "free_gb": round(stats["free"] / (1024 ** 3), 2),
                "percent": round(stats["percent"], 2),
            },
            "status": status.value,
        }

        if thresholds:
            log_data["thresholds"] = {
                "warning": round(thresholds["warning_threshold"], 2),
                "critical": round(thresholds["critical_threshold"], 2),
                "full": round(thresholds["full_threshold"], 2),
            }

        # Логируем с соответствующим уровнем
        if status == CapacityStatus.FULL:
            logger.critical("Storage capacity FULL - no new files accepted", extra=log_data)
        elif status == CapacityStatus.CRITICAL:
            logger.error("Storage capacity CRITICAL", extra=log_data)
        elif status == CapacityStatus.WARNING:
            logger.warning("Storage capacity WARNING", extra=log_data)
        else:
            logger.info("Storage capacity OK", extra=log_data)


# Глобальный экземпляр reporter (инициализируется в main.py)
_health_reporter: Optional[HealthReporter] = None


async def init_health_reporter(redis_client: Redis) -> HealthReporter:
    """
    Инициализация и запуск HealthReporter.

    Args:
        redis_client: Async Redis клиент

    Returns:
        HealthReporter: Запущенный экземпляр reporter
    """
    global _health_reporter

    _health_reporter = HealthReporter(redis_client)
    await _health_reporter.start()

    return _health_reporter


async def stop_health_reporter() -> None:
    """
    Остановка HealthReporter при shutdown.
    """
    global _health_reporter

    if _health_reporter:
        await _health_reporter.stop()
        _health_reporter = None


def get_health_reporter() -> Optional[HealthReporter]:
    """
    Получить текущий экземпляр HealthReporter.

    Returns:
        HealthReporter или None если не инициализирован
    """
    return _health_reporter
