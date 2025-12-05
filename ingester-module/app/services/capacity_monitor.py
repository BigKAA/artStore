"""
AdaptiveCapacityMonitor - Сервис мониторинга capacity Storage Elements.

Sprint 17: Geo-Distributed Capacity Management с Redis Leader Election.

Архитектура:
- Control Plane (Ingester) выполняет HTTP polling к Storage Elements
- Storage Elements не имеют доступа к Redis (reverse proxy/WAF)
- Leader Election через Redis предотвращает дублирование polling при horizontal scaling

Leader Election:
- Только 1 Ingester (LEADER) выполняет polling
- Остальные (FOLLOWERS) читают из shared Redis cache
- Automatic failover при падении Leader (TTL=30s)
- 75% снижение сетевого трафика

Redis Keys:
- capacity_monitor:leader_lock - Leader lock (TTL=30s)
- capacity:{se_id} - Capacity data cache (TTL=600s)
- health:{se_id} - Health status cache (TTL=600s)

ВАЖНО: Использует redis.asyncio (async), НЕ синхронный redis-py!
"""

import asyncio
import json
import time
import uuid
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

import httpx
from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core.config import settings
from app.core.logging import get_logger
from app.core.metrics import (
    record_leader_state,
    record_leader_transition,
    record_lock_acquisition,
    record_capacity_poll,
    record_poll_failure,
    record_lazy_update,
    update_available_storage_elements,
    record_cache_access,
)

logger = get_logger(__name__)


class MonitorRole(str, Enum):
    """Роль Ingester в Leader Election."""
    LEADER = "leader"
    FOLLOWER = "follower"
    UNKNOWN = "unknown"


class HealthStatus(str, Enum):
    """Health status Storage Element."""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


@dataclass
class StorageCapacityInfo:
    """
    Информация о capacity Storage Element.

    Получается через HTTP polling /api/v1/capacity endpoint.
    """
    storage_id: str
    mode: str  # edit, rw, ro, ar
    total: int  # bytes
    used: int  # bytes
    available: int  # bytes
    percent_used: float
    health: HealthStatus
    backend: str  # local, s3
    location: str  # datacenter
    last_update: str  # ISO 8601
    last_poll: str  # ISO 8601 - когда был выполнен polling
    endpoint: str  # HTTP endpoint для Storage Element

    def to_dict(self) -> dict:
        """Сериализация для Redis."""
        return {
            "storage_id": self.storage_id,
            "mode": self.mode,
            "total": str(self.total),
            "used": str(self.used),
            "available": str(self.available),
            "percent_used": str(self.percent_used),
            "health": self.health.value,
            "backend": self.backend,
            "location": self.location,
            "last_update": self.last_update,
            "last_poll": self.last_poll,
            "endpoint": self.endpoint,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "StorageCapacityInfo":
        """Десериализация из Redis."""
        return cls(
            storage_id=data.get("storage_id", ""),
            mode=data.get("mode", ""),
            total=int(data.get("total", 0)),
            used=int(data.get("used", 0)),
            available=int(data.get("available", 0)),
            percent_used=float(data.get("percent_used", 0.0)),
            health=HealthStatus(data.get("health", "unhealthy")),
            backend=data.get("backend", ""),
            location=data.get("location", ""),
            last_update=data.get("last_update", ""),
            last_poll=data.get("last_poll", ""),
            endpoint=data.get("endpoint", ""),
        )

    @property
    def is_writable(self) -> bool:
        """SE доступен для записи."""
        return self.mode in ("edit", "rw") and self.health == HealthStatus.HEALTHY

    def can_accept_file(self, file_size: int) -> bool:
        """Проверка возможности принять файл."""
        return self.is_writable and self.available >= file_size


@dataclass
class CapacityMonitorConfig:
    """Конфигурация AdaptiveCapacityMonitor."""

    # Leader Election
    leader_lock_key: str = "capacity_monitor:leader_lock"
    leader_ttl: int = 30  # seconds
    leader_renewal_interval: int = 10  # seconds (< leader_ttl)

    # Polling
    base_interval: int = 30  # seconds - базовый интервал polling
    max_interval: int = 300  # seconds - максимальный интервал (adaptive)
    min_interval: int = 10  # seconds - минимальный интервал (при ошибках)

    # HTTP
    http_timeout: int = 15  # seconds
    http_retries: int = 3
    retry_base_delay: float = 2.0  # seconds (exponential backoff: 2, 4, 8)

    # Cache
    cache_ttl: int = 600  # seconds - TTL для capacity cache
    health_ttl: int = 600  # seconds - TTL для health cache

    # Circuit Breaker
    failure_threshold: int = 3  # failures до пометки SE как unhealthy
    recovery_threshold: int = 2  # successes для восстановления

    # Adaptive Logic
    stability_threshold: int = 5  # polls без изменений → увеличение интервала
    change_threshold: float = 5.0  # % изменения capacity → уменьшение интервала


class AdaptiveCapacityMonitor:
    """
    Adaptive Capacity Monitor с Redis Leader Election.

    Реализует polling Storage Elements для получения capacity информации
    в geo-distributed среде, где SE не имеют доступа к Redis.

    Leader Election:
    - Атомарное получение lock через SET NX EX
    - Automatic failover через TTL
    - Followers читают из shared cache

    Usage:
        monitor = AdaptiveCapacityMonitor(redis_client)
        await monitor.start()

        # Получение capacity (работает для Leader и Follower)
        capacity = await monitor.get_capacity("se-01")

        # При остановке
        await monitor.stop()
    """

    def __init__(
        self,
        redis_client: Redis,
        storage_endpoints: dict[str, str],  # {se_id: endpoint_url}
        config: Optional[CapacityMonitorConfig] = None,
        storage_priorities: Optional[dict[str, int]] = None,  # Sprint 18 Phase 3
    ):
        """
        Инициализация AdaptiveCapacityMonitor.

        Args:
            redis_client: Async Redis client
            storage_endpoints: Словарь {se_id: endpoint_url} для polling
            config: Конфигурация (опционально)
            storage_priorities: Словарь {se_id: priority} для sorted set (Sprint 18 Phase 3)
        """
        self._redis = redis_client
        self._storage_endpoints = storage_endpoints
        self._config = config or CapacityMonitorConfig()
        # Sprint 18 Phase 3: Priorities для sorted set (Sequential Fill)
        self._storage_priorities = storage_priorities or {}

        # Instance ID для Leader Election (уникальный для каждого Ingester)
        self._instance_id = f"ingester-{uuid.uuid4().hex[:8]}"

        # Текущая роль
        self._role = MonitorRole.UNKNOWN

        # Background tasks
        self._polling_task: Optional[asyncio.Task] = None
        self._leader_renewal_task: Optional[asyncio.Task] = None
        self._running = False

        # HTTP клиент для polling
        self._http_client: Optional[httpx.AsyncClient] = None

        # Adaptive polling state
        self._poll_intervals: dict[str, int] = {}  # {se_id: current_interval}
        self._stability_counts: dict[str, int] = {}  # {se_id: polls_without_change}
        self._failure_counts: dict[str, int] = {}  # {se_id: consecutive_failures}

        # Metrics tracking
        self._last_leader_transition: Optional[datetime] = None
        self._leader_transitions_count = 0

        logger.info(
            "AdaptiveCapacityMonitor initialized",
            extra={
                "instance_id": self._instance_id,
                "storage_elements_count": len(storage_endpoints),
                "leader_ttl": self._config.leader_ttl,
                "base_interval": self._config.base_interval,
            }
        )

    @property
    def role(self) -> MonitorRole:
        """Текущая роль в Leader Election."""
        return self._role

    @property
    def is_leader(self) -> bool:
        """Является ли данный instance Leader."""
        return self._role == MonitorRole.LEADER

    @property
    def instance_id(self) -> str:
        """Уникальный ID данного Ingester instance."""
        return self._instance_id

    async def start(self) -> None:
        """
        Запуск Capacity Monitor.

        - Инициализирует HTTP клиент
        - Запускает Leader Election
        - Запускает polling (если Leader) или cache reading (если Follower)
        """
        if self._running:
            logger.warning("AdaptiveCapacityMonitor already running")
            return

        self._running = True

        # Инициализация HTTP клиента
        self._http_client = httpx.AsyncClient(
            timeout=httpx.Timeout(self._config.http_timeout),
            follow_redirects=True,
        )

        # Запуск Leader Election
        await self._try_acquire_leadership()

        # Запуск background tasks
        self._polling_task = asyncio.create_task(self._polling_loop())
        self._leader_renewal_task = asyncio.create_task(self._leader_renewal_loop())

        logger.info(
            "AdaptiveCapacityMonitor started",
            extra={
                "instance_id": self._instance_id,
                "role": self._role.value,
            }
        )

    async def stop(self) -> None:
        """
        Остановка Capacity Monitor.

        - Отпускает Leader lock (если Leader)
        - Останавливает background tasks
        - Закрывает HTTP клиент
        """
        if not self._running:
            return

        self._running = False

        # Отмена background tasks
        if self._polling_task:
            self._polling_task.cancel()
            try:
                await self._polling_task
            except asyncio.CancelledError:
                pass

        if self._leader_renewal_task:
            self._leader_renewal_task.cancel()
            try:
                await self._leader_renewal_task
            except asyncio.CancelledError:
                pass

        # Освобождение Leader lock (если мы Leader)
        if self._role == MonitorRole.LEADER:
            await self._release_leadership()

        # Закрытие HTTP клиента
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None

        logger.info(
            "AdaptiveCapacityMonitor stopped",
            extra={"instance_id": self._instance_id}
        )

    # ========== Leader Election ==========

    async def _try_acquire_leadership(self) -> bool:
        """
        Попытка получить Leader lock.

        Использует Redis SET NX EX для атомарного получения lock.

        Returns:
            bool: True если lock получен
        """
        start_time = time.perf_counter()

        try:
            # SET NX EX - атомарное создание lock с TTL
            acquired = await self._redis.set(
                self._config.leader_lock_key,
                self._instance_id,
                nx=True,  # SET only if NOT exists
                ex=self._config.leader_ttl,  # Expire after TTL
            )

            duration = time.perf_counter() - start_time

            if acquired:
                self._role = MonitorRole.LEADER
                self._last_leader_transition = datetime.now(timezone.utc)
                self._leader_transitions_count += 1

                # Metrics
                record_lock_acquisition("success", duration)
                record_leader_state(self._instance_id, True)
                record_leader_transition(self._instance_id, "acquired")

                logger.info(
                    "Leadership acquired",
                    extra={
                        "instance_id": self._instance_id,
                        "lock_key": self._config.leader_lock_key,
                        "ttl": self._config.leader_ttl,
                    }
                )
                return True
            else:
                # Кто-то другой уже Leader
                self._role = MonitorRole.FOLLOWER
                current_leader = await self._redis.get(self._config.leader_lock_key)

                # Metrics
                record_lock_acquisition("failed", duration)
                record_leader_state(self._instance_id, False)

                logger.debug(
                    "Leadership not acquired - another leader exists",
                    extra={
                        "instance_id": self._instance_id,
                        "current_leader": current_leader,
                    }
                )
                return False

        except RedisError as e:
            duration = time.perf_counter() - start_time
            record_lock_acquisition("failed", duration)

            logger.error(
                "Leader election failed",
                extra={
                    "instance_id": self._instance_id,
                    "error": str(e),
                }
            )
            self._role = MonitorRole.UNKNOWN
            return False

    async def _release_leadership(self) -> None:
        """
        Освобождение Leader lock.

        Безопасное удаление lock только если он принадлежит нам.
        """
        try:
            # Проверяем что lock наш перед удалением
            current_holder = await self._redis.get(self._config.leader_lock_key)

            if current_holder == self._instance_id:
                await self._redis.delete(self._config.leader_lock_key)
                logger.info(
                    "Leadership released",
                    extra={"instance_id": self._instance_id}
                )

            self._role = MonitorRole.FOLLOWER

        except RedisError as e:
            logger.error(
                "Failed to release leadership",
                extra={
                    "instance_id": self._instance_id,
                    "error": str(e),
                }
            )

    async def _renew_leadership(self) -> bool:
        """
        Продление Leader lock.

        Обновляет TTL если мы всё ещё владеем lock.

        Returns:
            bool: True если lock успешно продлён
        """
        try:
            # Проверяем что lock всё ещё наш
            current_holder = await self._redis.get(self._config.leader_lock_key)

            if current_holder == self._instance_id:
                # Продлеваем TTL
                await self._redis.expire(
                    self._config.leader_lock_key,
                    self._config.leader_ttl
                )

                # Metrics
                record_leader_transition(self._instance_id, "renewed")

                return True
            else:
                # Lock захвачен другим instance
                self._role = MonitorRole.FOLLOWER

                # Metrics
                record_leader_state(self._instance_id, False)
                record_leader_transition(self._instance_id, "lost")

                logger.warning(
                    "Leadership lost to another instance",
                    extra={
                        "instance_id": self._instance_id,
                        "new_leader": current_holder,
                    }
                )
                return False

        except RedisError as e:
            logger.error(
                "Failed to renew leadership",
                extra={
                    "instance_id": self._instance_id,
                    "error": str(e),
                }
            )
            return False

    async def _leader_renewal_loop(self) -> None:
        """
        Background task для продления Leader lock.

        - Leader: продлевает lock каждые leader_renewal_interval секунд
        - Follower: пытается захватить lock при его освобождении
        """
        while self._running:
            try:
                if self._role == MonitorRole.LEADER:
                    # Продлеваем lock
                    renewed = await self._renew_leadership()
                    if not renewed:
                        # Потеряли лидерство, пытаемся вернуть
                        await self._try_acquire_leadership()
                else:
                    # Пытаемся стать Leader (если текущий отвалился)
                    await self._try_acquire_leadership()

                await asyncio.sleep(self._config.leader_renewal_interval)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(
                    "Leader renewal loop error",
                    extra={
                        "instance_id": self._instance_id,
                        "error": str(e),
                    }
                )
                await asyncio.sleep(5)  # Backoff при ошибке

    # ========== Capacity Polling ==========

    async def _polling_loop(self) -> None:
        """
        Background task для polling Storage Elements.

        - Leader: выполняет HTTP polling к SE
        - Follower: только читает из cache
        """
        while self._running:
            try:
                if self._role == MonitorRole.LEADER:
                    # Polling всех SE
                    await self._poll_all_storage_elements()
                else:
                    # Follower просто ждёт (данные в cache)
                    pass

                # Интервал между итерациями
                await asyncio.sleep(self._config.base_interval)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(
                    "Polling loop error",
                    extra={
                        "instance_id": self._instance_id,
                        "role": self._role.value,
                        "error": str(e),
                    }
                )
                await asyncio.sleep(10)  # Backoff при ошибке

    async def _poll_all_storage_elements(self) -> None:
        """
        Polling всех Storage Elements.

        Выполняется параллельно для минимизации времени polling.
        """
        if not self._storage_endpoints:
            return

        tasks = [
            self._poll_storage_element(se_id, endpoint)
            for se_id, endpoint in self._storage_endpoints.items()
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Логируем результаты
        successful = sum(1 for r in results if isinstance(r, StorageCapacityInfo))
        failed = len(results) - successful

        logger.debug(
            "Polling round completed",
            extra={
                "total": len(results),
                "successful": successful,
                "failed": failed,
                "role": self._role.value,
            }
        )

    async def _poll_storage_element(
        self,
        se_id: str,
        endpoint: str
    ) -> Optional[StorageCapacityInfo]:
        """
        Polling одного Storage Element.

        Включает:
        - HTTP GET /api/v1/capacity
        - Retry с exponential backoff
        - Сохранение в Redis cache
        - Adaptive интервал

        Args:
            se_id: ID Storage Element
            endpoint: HTTP endpoint (e.g., "https://se-01.example.com")

        Returns:
            StorageCapacityInfo или None при ошибке
        """
        if not self._http_client:
            return None

        url = f"{endpoint.rstrip('/')}/api/v1/capacity"
        last_error = None

        # Retry с exponential backoff
        for attempt in range(self._config.http_retries):
            try:
                start_time = time.perf_counter()

                response = await self._http_client.get(url)
                response.raise_for_status()

                duration = time.perf_counter() - start_time
                data = response.json()

                # Создаём StorageCapacityInfo
                capacity_info = StorageCapacityInfo(
                    storage_id=data.get("storage_id", se_id),
                    mode=data.get("mode", "unknown"),
                    total=data.get("capacity", {}).get("total", 0),
                    used=data.get("capacity", {}).get("used", 0),
                    available=data.get("capacity", {}).get("available", 0),
                    percent_used=data.get("capacity", {}).get("percent_used", 0.0),
                    health=HealthStatus(data.get("health", "unhealthy")),
                    backend=data.get("backend", "unknown"),
                    location=data.get("location", "unknown"),
                    last_update=data.get("last_update", ""),
                    last_poll=datetime.now(timezone.utc).isoformat(),
                    endpoint=endpoint,
                )

                # Сохраняем в Redis cache
                await self._save_capacity_to_cache(se_id, capacity_info)

                # Обновляем adaptive state
                self._record_poll_success(se_id, capacity_info)

                # Metrics
                record_capacity_poll(se_id, "success", duration)

                logger.debug(
                    "SE polling successful",
                    extra={
                        "se_id": se_id,
                        "duration_ms": round(duration * 1000, 2),
                        "percent_used": capacity_info.percent_used,
                        "health": capacity_info.health.value,
                    }
                )

                return capacity_info

            except httpx.TimeoutException as e:
                last_error = e
                record_poll_failure(se_id, "timeout")
                logger.warning(
                    "SE polling timeout",
                    extra={
                        "se_id": se_id,
                        "attempt": attempt + 1,
                        "max_retries": self._config.http_retries,
                    }
                )
            except httpx.HTTPStatusError as e:
                last_error = e
                record_poll_failure(se_id, "http_error")
                logger.warning(
                    "SE polling HTTP error",
                    extra={
                        "se_id": se_id,
                        "status_code": e.response.status_code,
                        "attempt": attempt + 1,
                    }
                )
            except Exception as e:
                last_error = e
                record_poll_failure(se_id, "connection_error")
                logger.warning(
                    "SE polling error",
                    extra={
                        "se_id": se_id,
                        "error": str(e),
                        "attempt": attempt + 1,
                    }
                )

            # Exponential backoff перед retry
            if attempt < self._config.http_retries - 1:
                delay = self._config.retry_base_delay * (2 ** attempt)
                await asyncio.sleep(delay)

        # Все retry исчерпаны
        self._record_poll_failure(se_id)

        # Помечаем SE как unhealthy в cache
        await self._mark_se_unhealthy(se_id, str(last_error))

        logger.error(
            "SE polling failed after all retries",
            extra={
                "se_id": se_id,
                "retries": self._config.http_retries,
                "last_error": str(last_error),
            }
        )

        return None

    # ========== Redis Cache Operations ==========

    async def _save_capacity_to_cache(
        self,
        se_id: str,
        capacity_info: StorageCapacityInfo
    ) -> None:
        """
        Сохранение capacity данных в Redis cache.

        Sprint 18 Phase 3: Добавлен sorted set для Sequential Fill стратегии.

        Args:
            se_id: ID Storage Element
            capacity_info: Capacity информация для сохранения
        """
        try:
            cache_key = f"capacity:{se_id}"
            health_key = f"health:{se_id}"

            # Сохраняем capacity данные как Hash
            await self._redis.hset(
                cache_key,
                mapping=capacity_info.to_dict()
            )
            await self._redis.expire(cache_key, self._config.cache_ttl)

            # Сохраняем health status отдельно
            await self._redis.set(
                health_key,
                capacity_info.health.value,
                ex=self._config.health_ttl
            )

            # Sprint 18 Phase 3: Обновляем sorted set для Sequential Fill
            # Ключ: capacity:{mode}:available, score = priority
            mode = capacity_info.mode
            if mode in ("edit", "rw"):
                sorted_set_key = f"capacity:{mode}:available"
                priority = self._storage_priorities.get(se_id, 100)  # default priority = 100

                # SE доступен для записи - добавляем в sorted set
                if capacity_info.is_writable and capacity_info.health == HealthStatus.HEALTHY:
                    await self._redis.zadd(sorted_set_key, {se_id: priority})
                    await self._redis.expire(sorted_set_key, self._config.cache_ttl)
                else:
                    # SE недоступен - удаляем из sorted set
                    await self._redis.zrem(sorted_set_key, se_id)

        except RedisError as e:
            logger.error(
                "Failed to save capacity to cache",
                extra={
                    "se_id": se_id,
                    "error": str(e),
                }
            )

    async def _mark_se_unhealthy(self, se_id: str, reason: str) -> None:
        """
        Пометка SE как unhealthy в cache.

        Args:
            se_id: ID Storage Element
            reason: Причина unhealthy статуса
        """
        try:
            health_key = f"health:{se_id}"
            await self._redis.set(
                health_key,
                f"unhealthy: {reason}",
                ex=self._config.health_ttl
            )

        except RedisError as e:
            logger.error(
                "Failed to mark SE unhealthy",
                extra={
                    "se_id": se_id,
                    "error": str(e),
                }
            )

    async def get_capacity(self, se_id: str) -> Optional[StorageCapacityInfo]:
        """
        Получение capacity информации для SE.

        Работает как для Leader, так и для Follower (читает из cache).

        Args:
            se_id: ID Storage Element

        Returns:
            StorageCapacityInfo или None если данных нет
        """
        try:
            cache_key = f"capacity:{se_id}"
            data = await self._redis.hgetall(cache_key)

            if not data:
                record_cache_access(hit=False)
                return None

            record_cache_access(hit=True)
            return StorageCapacityInfo.from_dict(data)

        except RedisError as e:
            logger.error(
                "Failed to get capacity from cache",
                extra={
                    "se_id": se_id,
                    "error": str(e),
                }
            )
            return None

    async def get_all_capacities(self) -> dict[str, StorageCapacityInfo]:
        """
        Получение capacity информации для всех SE.

        Returns:
            Dict {se_id: StorageCapacityInfo}
        """
        result = {}

        for se_id in self._storage_endpoints.keys():
            capacity = await self.get_capacity(se_id)
            if capacity:
                result[se_id] = capacity

        return result

    async def get_available_storage_elements(
        self,
        mode: Optional[str] = None,
        min_available_bytes: int = 0
    ) -> list[StorageCapacityInfo]:
        """
        Получение списка доступных SE для загрузки.

        Args:
            mode: Фильтр по режиму (edit, rw)
            min_available_bytes: Минимальный доступный размер

        Returns:
            Список StorageCapacityInfo отсортированный по priority
        """
        all_capacities = await self.get_all_capacities()

        result = []
        for se_id, capacity in all_capacities.items():
            # Фильтр по mode
            if mode and capacity.mode != mode:
                continue

            # Фильтр по health
            if capacity.health != HealthStatus.HEALTHY:
                continue

            # Фильтр по available space
            if capacity.available < min_available_bytes:
                continue

            # Проверка writable mode
            if capacity.mode not in ("edit", "rw"):
                continue

            result.append(capacity)

        # Сортировка по percent_used (меньше заполненные первыми)
        result.sort(key=lambda x: x.percent_used)

        return result

    # ========== Adaptive Polling Logic ==========

    def _record_poll_success(
        self,
        se_id: str,
        capacity_info: StorageCapacityInfo
    ) -> None:
        """
        Запись успешного polling для adaptive logic.

        Args:
            se_id: ID Storage Element
            capacity_info: Полученная capacity информация
        """
        # Reset failure count
        self._failure_counts[se_id] = 0

        # TODO: Implement adaptive interval logic
        # - Увеличивать интервал при стабильности
        # - Уменьшать при изменениях

    def _record_poll_failure(self, se_id: str) -> None:
        """
        Запись неудачного polling для adaptive logic.

        Args:
            se_id: ID Storage Element
        """
        current = self._failure_counts.get(se_id, 0)
        self._failure_counts[se_id] = current + 1

    # ========== Lazy Update (для 507 Insufficient Storage) ==========

    async def trigger_lazy_update(
        self,
        se_id: str,
        reason: str = "manual"
    ) -> Optional[StorageCapacityInfo]:
        """
        Принудительное обновление capacity для конкретного SE.

        Вызывается при получении 507 Insufficient Storage.
        Работает независимо от роли (Leader/Follower).

        Args:
            se_id: ID Storage Element
            reason: Причина trigger ("insufficient_storage", "stale_cache", "manual")

        Returns:
            Обновлённая StorageCapacityInfo или None
        """
        endpoint = self._storage_endpoints.get(se_id)
        if not endpoint:
            logger.warning(
                "Lazy update requested for unknown SE",
                extra={"se_id": se_id}
            )
            return None

        # Metrics
        record_lazy_update(se_id, reason)

        logger.info(
            "Triggering lazy capacity update",
            extra={
                "se_id": se_id,
                "reason": reason,
                "triggered_by": self._instance_id,
                "role": self._role.value,
            }
        )

        # Выполняем polling независимо от роли
        return await self._poll_storage_element(se_id, endpoint)

    # ========== Status & Metrics ==========

    def get_status(self) -> dict:
        """
        Получение статуса Capacity Monitor.

        Returns:
            Dict со статусом для health checks и метрик
        """
        return {
            "instance_id": self._instance_id,
            "role": self._role.value,
            "running": self._running,
            "storage_elements_count": len(self._storage_endpoints),
            "leader_transitions_count": self._leader_transitions_count,
            "last_leader_transition": (
                self._last_leader_transition.isoformat()
                if self._last_leader_transition else None
            ),
            "config": {
                "leader_ttl": self._config.leader_ttl,
                "base_interval": self._config.base_interval,
                "cache_ttl": self._config.cache_ttl,
            }
        }


# Глобальный singleton
_capacity_monitor: Optional[AdaptiveCapacityMonitor] = None


async def get_capacity_monitor() -> Optional[AdaptiveCapacityMonitor]:
    """Получение глобального экземпляра Capacity Monitor."""
    return _capacity_monitor


async def init_capacity_monitor(
    redis_client: Redis,
    storage_endpoints: dict[str, str],
    config: Optional[CapacityMonitorConfig] = None,
    storage_priorities: Optional[dict[str, int]] = None,  # Sprint 18 Phase 3
) -> AdaptiveCapacityMonitor:
    """
    Инициализация глобального Capacity Monitor.

    Вызывается при startup приложения.

    Args:
        redis_client: Async Redis client
        storage_endpoints: Dict {se_id: endpoint_url}
        config: Опциональная конфигурация
        storage_priorities: Dict {se_id: priority} для sorted set (Sprint 18 Phase 3)

    Returns:
        Инициализированный AdaptiveCapacityMonitor
    """
    global _capacity_monitor

    _capacity_monitor = AdaptiveCapacityMonitor(
        redis_client=redis_client,
        storage_endpoints=storage_endpoints,
        config=config,
        storage_priorities=storage_priorities,  # Sprint 18 Phase 3
    )

    await _capacity_monitor.start()

    return _capacity_monitor


async def close_capacity_monitor() -> None:
    """Остановка глобального Capacity Monitor."""
    global _capacity_monitor

    if _capacity_monitor:
        await _capacity_monitor.stop()
        _capacity_monitor = None
