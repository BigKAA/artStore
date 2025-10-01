"""
Сервис для работы с Redis.
Обеспечивает Service Discovery для storage elements.
"""
import json
from typing import Optional, Dict, List, Any
from datetime import datetime
import redis
from redis.exceptions import RedisError, ConnectionError as RedisConnectionError

from app.config import settings
from app.utils.logger import get_logger

logger = get_logger(__name__)


class RedisService:
    """
    Сервис для работы с Redis (синхронный).
    Используется для Service Discovery и координации кластера.
    """

    def __init__(self):
        """
        Инициализация Redis клиента.
        """
        self._client: Optional[redis.Redis] = None
        self._is_connected = False

    def connect(self) -> bool:
        """
        Подключение к Redis.

        Returns:
            True если подключение успешно
        """
        try:
            self._client = redis.Redis(
                host=settings.redis.host,
                port=settings.redis.port,
                password=settings.redis.password if settings.redis.password else None,
                db=settings.redis.db,
                decode_responses=True,  # Автоматическая декодировка строк
                socket_connect_timeout=5,
                socket_timeout=5,
                retry_on_timeout=True,
                health_check_interval=30
            )

            # Проверка подключения
            self._client.ping()
            self._is_connected = True
            logger.info(f"Успешное подключение к Redis: {settings.redis.host}:{settings.redis.port}")
            return True

        except RedisConnectionError as e:
            logger.error(f"Ошибка подключения к Redis: {e}")
            self._is_connected = False
            return False
        except Exception as e:
            logger.error(f"Неожиданная ошибка при подключении к Redis: {e}")
            self._is_connected = False
            return False

    def disconnect(self):
        """
        Отключение от Redis.
        """
        if self._client:
            try:
                self._client.close()
                logger.info("Отключение от Redis")
            except Exception as e:
                logger.error(f"Ошибка при отключении от Redis: {e}")
            finally:
                self._client = None
                self._is_connected = False

    def is_connected(self) -> bool:
        """
        Проверка подключения к Redis.

        Returns:
            True если подключен
        """
        if not self._client or not self._is_connected:
            return False

        try:
            self._client.ping()
            return True
        except RedisError:
            self._is_connected = False
            return False

    def _ensure_connected(self):
        """
        Проверка подключения и автоматическое переподключение.

        Raises:
            ConnectionError: Если невозможно подключиться
        """
        if not self.is_connected():
            if not self.connect():
                raise ConnectionError("Не удалось подключиться к Redis")

    # Service Discovery методы

    def publish_storage_element(
        self,
        element_id: str,
        config: Dict[str, Any]
    ) -> bool:
        """
        Публикует конфигурацию storage element в Redis.

        Args:
            element_id: ID элемента хранения
            config: Конфигурация элемента

        Returns:
            True если успешно
        """
        try:
            self._ensure_connected()

            # Ключ для хранения конфигурации
            key = f"storage_element:{element_id}"

            # Добавляем метаданные
            config_with_meta = {
                **config,
                "published_at": datetime.utcnow().isoformat(),
                "published_by": "admin-module"
            }

            # Сохраняем в Redis
            self._client.set(
                key,
                json.dumps(config_with_meta),
                ex=settings.redis.storage_element_ttl  # TTL в секундах
            )

            # Публикуем событие об изменении
            self._client.publish(
                "storage_elements:updates",
                json.dumps({
                    "event": "updated",
                    "element_id": element_id,
                    "timestamp": datetime.utcnow().isoformat()
                })
            )

            logger.info(f"Опубликована конфигурация storage element: {element_id}")
            return True

        except Exception as e:
            logger.error(f"Ошибка публикации storage element {element_id}: {e}")
            return False

    def get_storage_element(self, element_id: str) -> Optional[Dict[str, Any]]:
        """
        Получает конфигурацию storage element из Redis.

        Args:
            element_id: ID элемента хранения

        Returns:
            Конфигурация или None если не найдена
        """
        try:
            self._ensure_connected()

            key = f"storage_element:{element_id}"
            data = self._client.get(key)

            if data:
                return json.loads(data)
            return None

        except Exception as e:
            logger.error(f"Ошибка получения storage element {element_id}: {e}")
            return None

    def get_all_storage_elements(self) -> List[Dict[str, Any]]:
        """
        Получает все storage elements из Redis.

        Returns:
            Список конфигураций
        """
        try:
            self._ensure_connected()

            # Получаем все ключи storage elements
            pattern = "storage_element:*"
            keys = self._client.keys(pattern)

            elements = []
            for key in keys:
                data = self._client.get(key)
                if data:
                    config = json.loads(data)
                    elements.append(config)

            logger.debug(f"Получено {len(elements)} storage elements из Redis")
            return elements

        except Exception as e:
            logger.error(f"Ошибка получения списка storage elements: {e}")
            return []

    def delete_storage_element(self, element_id: str) -> bool:
        """
        Удаляет storage element из Redis.

        Args:
            element_id: ID элемента хранения

        Returns:
            True если успешно
        """
        try:
            self._ensure_connected()

            key = f"storage_element:{element_id}"
            deleted = self._client.delete(key)

            # Публикуем событие об удалении
            if deleted:
                self._client.publish(
                    "storage_elements:updates",
                    json.dumps({
                        "event": "deleted",
                        "element_id": element_id,
                        "timestamp": datetime.utcnow().isoformat()
                    })
                )

            logger.info(f"Удален storage element из Redis: {element_id}")
            return bool(deleted)

        except Exception as e:
            logger.error(f"Ошибка удаления storage element {element_id}: {e}")
            return False

    # Raft Cluster методы

    def set_cluster_leader(self, node_id: str, node_info: Dict[str, Any]) -> bool:
        """
        Устанавливает текущего лидера Raft кластера.

        Args:
            node_id: ID узла-лидера
            node_info: Информация о лидере

        Returns:
            True если успешно
        """
        try:
            self._ensure_connected()

            leader_data = {
                "node_id": node_id,
                "elected_at": datetime.utcnow().isoformat(),
                **node_info
            }

            self._client.set(
                "cluster:leader",
                json.dumps(leader_data),
                ex=30  # TTL 30 секунд (heartbeat должен обновлять)
            )

            # Публикуем событие о новом лидере
            self._client.publish(
                "cluster:events",
                json.dumps({
                    "event": "leader_elected",
                    "node_id": node_id,
                    "timestamp": datetime.utcnow().isoformat()
                })
            )

            logger.info(f"Установлен лидер кластера: {node_id}")
            return True

        except Exception as e:
            logger.error(f"Ошибка установки лидера кластера: {e}")
            return False

    def get_cluster_leader(self) -> Optional[Dict[str, Any]]:
        """
        Получает информацию о текущем лидере кластера.

        Returns:
            Информация о лидере или None
        """
        try:
            self._ensure_connected()

            data = self._client.get("cluster:leader")
            if data:
                return json.loads(data)
            return None

        except Exception as e:
            logger.error(f"Ошибка получения информации о лидере: {e}")
            return None

    def heartbeat_leader(self, node_id: str) -> bool:
        """
        Обновляет TTL лидера (heartbeat).

        Args:
            node_id: ID узла-лидера

        Returns:
            True если успешно
        """
        try:
            self._ensure_connected()

            # Проверяем, что мы действительно лидер
            current_leader = self.get_cluster_leader()
            if not current_leader or current_leader.get("node_id") != node_id:
                logger.warning(f"Узел {node_id} не является лидером")
                return False

            # Обновляем TTL
            self._client.expire("cluster:leader", 30)
            return True

        except Exception as e:
            logger.error(f"Ошибка heartbeat лидера: {e}")
            return False

    # Общие методы

    def set(self, key: str, value: str, ex: Optional[int] = None) -> bool:
        """
        Сохраняет значение в Redis.

        Args:
            key: Ключ
            value: Значение
            ex: TTL в секундах (опционально)

        Returns:
            True если успешно
        """
        try:
            self._ensure_connected()
            self._client.set(key, value, ex=ex)
            return True
        except Exception as e:
            logger.error(f"Ошибка записи в Redis (key={key}): {e}")
            return False

    def get(self, key: str) -> Optional[str]:
        """
        Получает значение из Redis.

        Args:
            key: Ключ

        Returns:
            Значение или None
        """
        try:
            self._ensure_connected()
            return self._client.get(key)
        except Exception as e:
            logger.error(f"Ошибка чтения из Redis (key={key}): {e}")
            return None

    def delete(self, key: str) -> bool:
        """
        Удаляет значение из Redis.

        Args:
            key: Ключ

        Returns:
            True если успешно
        """
        try:
            self._ensure_connected()
            deleted = self._client.delete(key)
            return bool(deleted)
        except Exception as e:
            logger.error(f"Ошибка удаления из Redis (key={key}): {e}")
            return False

    def ping(self) -> bool:
        """
        Проверяет доступность Redis.

        Returns:
            True если доступен
        """
        try:
            if self._client:
                self._client.ping()
                return True
            return False
        except Exception:
            return False


# Глобальный экземпляр сервиса
redis_service = RedisService()
