"""
Сервис публикации конфигурации Storage Elements в Redis.

Отвечает за:
- Формирование конфигурации всех активных Storage Elements
- Публикацию конфигурации в Redis для Service Discovery
- Периодическую публикацию по расписанию
- Событийную публикацию при CRUD операциях

Ingester и Query модули подписываются на канал Redis Pub/Sub
и получают обновленную конфигурацию в реальном времени.
"""

import logging
from datetime import datetime
from typing import Optional, List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.redis import service_discovery, publish_storage_element_config_standalone
from app.models.storage_element import StorageElement, StorageStatus, StorageMode

logger = logging.getLogger(__name__)


class StorageElementPublishService:
    """
    Сервис публикации конфигурации Storage Elements в Redis.

    Формирует JSON конфигурацию всех активных storage elements
    и публикует её в Redis для Service Discovery.

    Формат конфигурации (сохраняется в Redis key artstore:storage_elements):
    {
        "version": 1,
        "timestamp": "2025-11-28T12:00:00.000Z",
        "count": 2,
        "storage_elements": [
            {
                "id": 1,
                "name": "storage-element-1",
                "api_url": "http://storage-element-1:8010",
                "mode": "edit",
                "storage_type": "local",
                "status": "online",
                "capacity_bytes": 10737418240,
                "used_bytes": 1073741824,
                "file_count": 100,
                "priority": 100,
                "element_id": "se-local-01",
                "is_writable": true,
                "is_available": true
            }
        ]
    }

    Формат события Pub/Sub (публикуется в канал artstore:service_discovery):
    {
        "event": "storage_element_config_updated",
        "timestamp": "2025-11-28T12:00:00.000Z",
        "action": "created|updated|deleted|synced|scheduled|startup",
        "version": 1,
        "count": 2,
        "storage_element_id": 1,  # Опционально, для событийных операций
        "storage_element_name": "storage-element-1"  # Опционально
    }
    """

    # Счетчик версий для отслеживания изменений
    _version_counter: int = 0

    async def get_all_active_storage_elements(
        self,
        db: AsyncSession
    ) -> List[StorageElement]:
        """
        Получение всех активных Storage Elements из БД.

        Фильтрует по статусам: ONLINE и DEGRADED.
        Storage elements в статусах OFFLINE и MAINTENANCE не включаются.

        Args:
            db: AsyncSession для работы с БД

        Returns:
            List[StorageElement]: Список активных storage elements
        """
        query = select(StorageElement).where(
            StorageElement.status.in_([StorageStatus.ONLINE, StorageStatus.DEGRADED])
        ).order_by(StorageElement.id)

        result = await db.execute(query)
        return list(result.scalars().all())

    async def get_all_storage_elements(
        self,
        db: AsyncSession
    ) -> List[StorageElement]:
        """
        Получение всех Storage Elements из БД (включая offline).

        Используется для полной публикации при startup и sync.

        Args:
            db: AsyncSession для работы с БД

        Returns:
            List[StorageElement]: Список всех storage elements
        """
        query = select(StorageElement).order_by(StorageElement.id)
        result = await db.execute(query)
        return list(result.scalars().all())

    def _build_storage_element_config(
        self,
        storage_elements: List[StorageElement]
    ) -> dict:
        """
        Формирование конфигурации для публикации в Redis.

        Args:
            storage_elements: Список storage elements

        Returns:
            dict: Конфигурация в формате JSON-serializable dict
        """
        StorageElementPublishService._version_counter += 1

        elements_data = []
        for se in storage_elements:
            # Вычисляем is_available и is_writable
            is_available = se.status == StorageStatus.ONLINE
            is_writable = se.mode in (StorageMode.EDIT, StorageMode.RW) and is_available

            elements_data.append({
                "id": se.id,
                "name": se.name,
                "api_url": se.api_url,
                "mode": se.mode.value if isinstance(se.mode, StorageMode) else se.mode,
                "storage_type": se.storage_type.value if hasattr(se.storage_type, 'value') else se.storage_type,
                "status": se.status.value if isinstance(se.status, StorageStatus) else se.status,
                "base_path": se.base_path,
                "capacity_bytes": se.capacity_bytes,
                "used_bytes": se.used_bytes,
                "file_count": se.file_count,
                "retention_days": se.retention_days,
                # Service Discovery (Sequential Fill) - Sprint 14
                "priority": se.priority,
                "element_id": se.element_id,
                "is_writable": is_writable,
                "is_available": is_available,
                "last_health_check": se.last_health_check.isoformat() if se.last_health_check else None
            })

        return {
            "version": StorageElementPublishService._version_counter,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "count": len(elements_data),
            "storage_elements": elements_data
        }

    async def publish_all_storage_elements(
        self,
        db: AsyncSession,
        action: str = "manual",
        storage_element_id: Optional[int] = None,
        storage_element_name: Optional[str] = None,
        include_offline: bool = True
    ) -> int:
        """
        Публикация конфигурации всех Storage Elements в Redis.

        Основной метод для публикации. Получает все storage elements из БД,
        формирует конфигурацию и публикует в Redis.

        Args:
            db: AsyncSession для работы с БД
            action: Тип действия (created/updated/deleted/synced/scheduled/startup)
            storage_element_id: ID измененного storage element (опционально)
            storage_element_name: Имя измененного storage element (опционально)
            include_offline: Включать ли offline storage elements

        Returns:
            int: Количество подписчиков, получивших обновление
        """
        if not settings.service_discovery.enabled:
            logger.debug("Service Discovery отключен, публикация пропущена")
            return 0

        try:
            # Получаем storage elements
            if include_offline:
                storage_elements = await self.get_all_storage_elements(db)
            else:
                storage_elements = await self.get_all_active_storage_elements(db)

            # Формируем конфигурацию
            config = self._build_storage_element_config(storage_elements)

            # Публикуем через ServiceDiscovery
            subscribers = await service_discovery.publish_storage_element_config(
                config=config,
                action=action,
                storage_element_id=storage_element_id,
                storage_element_name=storage_element_name
            )

            logger.info(
                f"Опубликована конфигурация storage elements: "
                f"action={action}, count={config['count']}, "
                f"version={config['version']}, subscribers={subscribers}"
            )

            return subscribers

        except Exception as e:
            logger.error(
                f"Ошибка публикации конфигурации storage elements: {e}",
                exc_info=True
            )
            return 0

    async def publish_on_create(
        self,
        db: AsyncSession,
        storage_element: StorageElement
    ) -> int:
        """
        Публикация при создании нового Storage Element.

        Args:
            db: AsyncSession
            storage_element: Созданный storage element

        Returns:
            int: Количество подписчиков
        """
        return await self.publish_all_storage_elements(
            db=db,
            action="created",
            storage_element_id=storage_element.id,
            storage_element_name=storage_element.name
        )

    async def publish_on_update(
        self,
        db: AsyncSession,
        storage_element: StorageElement
    ) -> int:
        """
        Публикация при обновлении Storage Element.

        Args:
            db: AsyncSession
            storage_element: Обновленный storage element

        Returns:
            int: Количество подписчиков
        """
        return await self.publish_all_storage_elements(
            db=db,
            action="updated",
            storage_element_id=storage_element.id,
            storage_element_name=storage_element.name
        )

    async def publish_on_delete(
        self,
        db: AsyncSession,
        storage_element_id: int,
        storage_element_name: str
    ) -> int:
        """
        Публикация при удалении Storage Element.

        Args:
            db: AsyncSession
            storage_element_id: ID удаленного storage element
            storage_element_name: Имя удаленного storage element

        Returns:
            int: Количество подписчиков
        """
        return await self.publish_all_storage_elements(
            db=db,
            action="deleted",
            storage_element_id=storage_element_id,
            storage_element_name=storage_element_name
        )

    async def publish_on_sync(
        self,
        db: AsyncSession,
        storage_element: Optional[StorageElement] = None
    ) -> int:
        """
        Публикация после синхронизации Storage Element(s).

        Args:
            db: AsyncSession
            storage_element: Синхронизированный storage element (опционально)

        Returns:
            int: Количество подписчиков
        """
        return await self.publish_all_storage_elements(
            db=db,
            action="synced",
            storage_element_id=storage_element.id if storage_element else None,
            storage_element_name=storage_element.name if storage_element else None
        )

    async def publish_scheduled(self, db: AsyncSession) -> int:
        """
        Периодическая публикация по расписанию (используется в FastAPI context).

        Вызывается APScheduler каждые N секунд (настраивается в config).
        Для background jobs используйте publish_scheduled_standalone().

        Args:
            db: AsyncSession

        Returns:
            int: Количество подписчиков
        """
        return await self.publish_all_storage_elements(
            db=db,
            action="scheduled"
        )

    async def publish_scheduled_standalone(self, db: AsyncSession) -> int:
        """
        Периодическая публикация для background jobs (отдельный event loop).

        Использует standalone Redis client, который работает в отдельном event loop.
        ВАЖНО: Используйте этот метод ТОЛЬКО в APScheduler background jobs,
        для FastAPI endpoints используйте publish_scheduled().

        Args:
            db: AsyncSession (standalone, созданный через create_standalone_async_session)

        Returns:
            int: Количество подписчиков
        """
        if not settings.service_discovery.enabled:
            logger.debug("Service Discovery отключен, публикация пропущена")
            return 0

        try:
            # Получаем storage elements
            storage_elements = await self.get_all_storage_elements(db)

            # Формируем конфигурацию
            config = self._build_storage_element_config(storage_elements)

            # Публикуем через standalone функцию (собственный Redis client)
            subscribers = await publish_storage_element_config_standalone(
                config=config,
                action="scheduled"
            )

            logger.info(
                f"Опубликована конфигурация storage elements (standalone): "
                f"action=scheduled, count={config['count']}, "
                f"version={config['version']}, subscribers={subscribers}"
            )

            return subscribers

        except Exception as e:
            logger.error(
                f"Ошибка публикации конфигурации storage elements (standalone): {e}",
                exc_info=True
            )
            return 0

    async def publish_startup(self, db: AsyncSession) -> int:
        """
        Публикация при запуске приложения.

        Вызывается один раз при startup для initial population Redis.

        Args:
            db: AsyncSession

        Returns:
            int: Количество подписчиков
        """
        return await self.publish_all_storage_elements(
            db=db,
            action="startup"
        )


# Глобальный экземпляр сервиса
storage_element_publish_service = StorageElementPublishService()
