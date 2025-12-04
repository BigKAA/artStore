"""
Storage Sync Service для синхронизации информации о storage elements.

Сервис для периодической и ручной синхронизации данных
storage elements с их актуальным состоянием.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.storage_element import (
    StorageElement,
    StorageMode,
    StorageStatus,
)
from app.core.exceptions import (
    StorageElementNotFoundError,
    StorageElementDiscoveryError,
)
from app.services.storage_discovery_service import (
    StorageDiscoveryService,
    StorageElementDiscoveryResult,
)
from app.services.storage_element_publish_service import storage_element_publish_service

logger = logging.getLogger(__name__)


@dataclass
class SyncChange:
    """Описание одного изменения при синхронизации."""
    field: str
    old_value: str
    new_value: str


@dataclass
class SyncResult:
    """
    Результат синхронизации одного storage element.
    """
    storage_element_id: int
    storage_element_name: str
    success: bool
    error: Optional[str] = None
    changes: List[SyncChange] = field(default_factory=list)
    synced_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def has_changes(self) -> bool:
        """Были ли изменения при синхронизации."""
        return len(self.changes) > 0


class StorageSyncService:
    """
    Сервис для синхронизации состояния storage elements.

    Функции:
    - Ручная синхронизация отдельного storage element
    - Массовая синхронизация всех storage elements
    - Отслеживание изменений (diff) при синхронизации
    """

    def __init__(self, discovery_service: Optional[StorageDiscoveryService] = None):
        """
        Инициализация сервиса.

        Args:
            discovery_service: Сервис для discovery (опционально, создается по умолчанию)
        """
        self.discovery_service = discovery_service or StorageDiscoveryService()

    def _map_status(self, discovered_status: str) -> StorageStatus:
        """
        Маппинг статуса из discovery в StorageStatus enum.

        Args:
            discovered_status: Статус от storage element

        Returns:
            StorageStatus: Mapped статус
        """
        status_map = {
            "operational": StorageStatus.ONLINE,
            "degraded": StorageStatus.DEGRADED,
            "maintenance": StorageStatus.MAINTENANCE,
            "offline": StorageStatus.OFFLINE,
        }
        return status_map.get(discovered_status, StorageStatus.ONLINE)

    def _map_mode(self, discovered_mode: str) -> StorageMode:
        """
        Маппинг mode из discovery в StorageMode enum.

        Args:
            discovered_mode: Mode от storage element

        Returns:
            StorageMode: Mapped mode
        """
        mode_map = {
            "edit": StorageMode.EDIT,
            "rw": StorageMode.RW,
            "ro": StorageMode.RO,
            "ar": StorageMode.AR,
        }
        return mode_map.get(discovered_mode, StorageMode.RW)

    def _collect_changes(
        self,
        storage_element: StorageElement,
        discovery_result: StorageElementDiscoveryResult
    ) -> List[SyncChange]:
        """
        Собрать список изменений между текущим состоянием и discovered.

        Args:
            storage_element: Текущее состояние в БД
            discovery_result: Данные от storage element

        Returns:
            List[SyncChange]: Список изменений
        """
        changes = []

        # Проверяем mode
        new_mode = self._map_mode(discovery_result.mode)
        if storage_element.mode != new_mode:
            changes.append(SyncChange(
                field="mode",
                old_value=storage_element.mode.value,
                new_value=new_mode.value
            ))

        # Проверяем status
        new_status = self._map_status(discovery_result.status)
        if storage_element.status != new_status:
            changes.append(SyncChange(
                field="status",
                old_value=storage_element.status.value,
                new_value=new_status.value
            ))

        # Проверяем capacity_bytes
        if storage_element.capacity_bytes != discovery_result.capacity_bytes:
            changes.append(SyncChange(
                field="capacity_bytes",
                old_value=str(storage_element.capacity_bytes),
                new_value=str(discovery_result.capacity_bytes)
            ))

        # Проверяем used_bytes
        if storage_element.used_bytes != discovery_result.used_bytes:
            changes.append(SyncChange(
                field="used_bytes",
                old_value=str(storage_element.used_bytes),
                new_value=str(discovery_result.used_bytes)
            ))

        # Проверяем file_count
        if storage_element.file_count != discovery_result.file_count:
            changes.append(SyncChange(
                field="file_count",
                old_value=str(storage_element.file_count),
                new_value=str(discovery_result.file_count)
            ))

        return changes

    def _apply_changes(
        self,
        storage_element: StorageElement,
        discovery_result: StorageElementDiscoveryResult
    ) -> None:
        """
        Применить изменения к storage element.

        Args:
            storage_element: Объект для обновления
            discovery_result: Данные от storage element
        """
        storage_element.mode = self._map_mode(discovery_result.mode)
        storage_element.status = self._map_status(discovery_result.status)
        storage_element.capacity_bytes = discovery_result.capacity_bytes
        storage_element.used_bytes = discovery_result.used_bytes
        storage_element.file_count = discovery_result.file_count
        storage_element.last_health_check = datetime.now(timezone.utc)

    async def sync_storage_element(
        self,
        db: AsyncSession,
        storage_element_id: int
    ) -> SyncResult:
        """
        Синхронизировать один storage element.

        Получает актуальную информацию от storage element через discovery
        и обновляет данные в БД.

        Args:
            db: Сессия базы данных
            storage_element_id: ID storage element

        Returns:
            SyncResult: Результат синхронизации

        Raises:
            StorageElementNotFoundError: Storage element не найден
        """
        # Получаем storage element из БД
        result = await db.execute(
            select(StorageElement).where(StorageElement.id == storage_element_id)
        )
        storage_element = result.scalar_one_or_none()

        if not storage_element:
            raise StorageElementNotFoundError(storage_element_id)

        logger.info(
            f"Начало синхронизации storage element {storage_element.name} "
            f"(ID: {storage_element_id})"
        )

        try:
            # Выполняем discovery
            discovery_result = await self.discovery_service.discover_storage_element(
                storage_element.api_url
            )

            # Собираем изменения
            changes = self._collect_changes(storage_element, discovery_result)

            # Применяем изменения
            self._apply_changes(storage_element, discovery_result)

            await db.commit()

            # Публикуем обновления в Redis для Service Discovery
            # Это критически важно для корректной работы Sequential Fill Algorithm
            if changes:
                logger.info(
                    f"Синхронизация {storage_element.name}: "
                    f"{len(changes)} изменений применено"
                )
                for change in changes:
                    logger.debug(
                        f"  {change.field}: {change.old_value} -> {change.new_value}"
                    )
                # Публикуем в Redis только если были изменения
                await storage_element_publish_service.publish_on_sync(
                    db, storage_element
                )
            else:
                logger.debug(f"Синхронизация {storage_element.name}: без изменений")

            return SyncResult(
                storage_element_id=storage_element_id,
                storage_element_name=storage_element.name,
                success=True,
                changes=changes
            )

        except StorageElementDiscoveryError as e:
            logger.warning(
                f"Ошибка синхронизации {storage_element.name}: {e}"
            )

            # При ошибке discovery - помечаем как offline
            storage_element.status = StorageStatus.OFFLINE
            storage_element.last_health_check = datetime.now(timezone.utc)
            await db.commit()

            # Публикуем изменение статуса в Redis
            await storage_element_publish_service.publish_on_sync(
                db, storage_element
            )

            return SyncResult(
                storage_element_id=storage_element_id,
                storage_element_name=storage_element.name,
                success=False,
                error=str(e),
                changes=[SyncChange(
                    field="status",
                    old_value=storage_element.status.value,
                    new_value=StorageStatus.OFFLINE.value
                )]
            )

        except Exception as e:
            logger.error(
                f"Неожиданная ошибка синхронизации {storage_element.name}: {e}"
            )
            await db.rollback()

            return SyncResult(
                storage_element_id=storage_element_id,
                storage_element_name=storage_element.name,
                success=False,
                error=f"Неожиданная ошибка: {e}"
            )

    async def sync_all_storage_elements(
        self,
        db: AsyncSession,
        only_online: bool = True
    ) -> List[SyncResult]:
        """
        Синхронизировать все storage elements.

        Args:
            db: Сессия базы данных
            only_online: Синхронизировать только online элементы

        Returns:
            List[SyncResult]: Результаты синхронизации
        """
        # Получаем список storage elements
        query = select(StorageElement)
        if only_online:
            query = query.where(StorageElement.status == StorageStatus.ONLINE)

        result = await db.execute(query)
        storage_elements = result.scalars().all()

        logger.info(f"Начало массовой синхронизации: {len(storage_elements)} элементов")

        results = []
        for storage_element in storage_elements:
            sync_result = await self.sync_storage_element(db, storage_element.id)
            results.append(sync_result)

        # Подсчитываем статистику
        success_count = sum(1 for r in results if r.success)
        failed_count = len(results) - success_count
        changes_count = sum(len(r.changes) for r in results)

        logger.info(
            f"Массовая синхронизация завершена: "
            f"{success_count} успешно, {failed_count} ошибок, "
            f"{changes_count} изменений всего"
        )

        return results


# Глобальный экземпляр сервиса
storage_sync_service = StorageSyncService()
