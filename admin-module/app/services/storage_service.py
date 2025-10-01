"""
Сервис для работы с Storage Elements.
Управляет элементами хранения и публикует их конфигурацию в Redis.
"""
from typing import Optional, List, Tuple, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_, and_
from sqlalchemy.exc import IntegrityError
from datetime import datetime

from app.db.models.storage_element import StorageElement
from app.schemas.storage_element import (
    StorageElementCreate,
    StorageElementUpdate,
    StorageElementSearchParams,
    StorageElementStats
)
from app.services.redis_service import redis_service
from app.utils.logger import get_logger

logger = get_logger(__name__)


class StorageService:
    """
    Сервис управления Storage Elements.
    Координирует БД операции и Service Discovery через Redis.
    """

    async def create_storage_element(
        self,
        db: AsyncSession,
        element_data: StorageElementCreate
    ) -> StorageElement:
        """
        Создает новый элемент хранения.

        Args:
            db: Database session
            element_data: Данные для создания

        Returns:
            Созданный элемент хранения

        Raises:
            ValueError: Если name уже существует
        """
        # Проверка уникальности name
        existing = await self.get_storage_element_by_name(db, element_data.name)
        if existing:
            raise ValueError(f"Storage element с именем '{element_data.name}' уже существует")

        # Создание элемента
        storage_element = StorageElement(
            name=element_data.name,
            description=element_data.description,
            storage_type=element_data.storage_type,
            base_url=element_data.base_url,
            mode=element_data.mode,
            retention_days=element_data.retention_days,
            max_size_gb=element_data.max_size_gb,
            current_size_gb=0.0,
            is_active=True,
            config=element_data.config
        )

        db.add(storage_element)

        try:
            await db.commit()
            await db.refresh(storage_element)

            # Публикация в Redis для Service Discovery
            self._publish_to_redis(storage_element)

            logger.info(f"Создан storage element: {storage_element.name} (ID: {storage_element.id})")
            return storage_element

        except IntegrityError as e:
            await db.rollback()
            logger.error(f"Ошибка создания storage element: {e}")
            raise ValueError("Ошибка создания storage element. Возможно, имя не уникально.")

    async def get_storage_element_by_id(
        self,
        db: AsyncSession,
        element_id: str
    ) -> Optional[StorageElement]:
        """
        Получает элемент хранения по ID.

        Args:
            db: Database session
            element_id: ID элемента

        Returns:
            StorageElement или None
        """
        result = await db.execute(
            select(StorageElement).where(StorageElement.id == element_id)
        )
        return result.scalar_one_or_none()

    async def get_storage_element_by_name(
        self,
        db: AsyncSession,
        name: str
    ) -> Optional[StorageElement]:
        """
        Получает элемент хранения по имени.

        Args:
            db: Database session
            name: Имя элемента

        Returns:
            StorageElement или None
        """
        result = await db.execute(
            select(StorageElement).where(StorageElement.name == name)
        )
        return result.scalar_one_or_none()

    async def update_storage_element(
        self,
        db: AsyncSession,
        element_id: str,
        element_data: StorageElementUpdate
    ) -> Optional[StorageElement]:
        """
        Обновляет элемент хранения.

        Args:
            db: Database session
            element_id: ID элемента
            element_data: Данные для обновления

        Returns:
            Обновленный элемент или None

        Raises:
            ValueError: Если валидация не прошла
        """
        element = await self.get_storage_element_by_id(db, element_id)
        if not element:
            return None

        # Обновление полей (только если они переданы)
        if element_data.description is not None:
            element.description = element_data.description

        if element_data.base_url is not None:
            element.base_url = element_data.base_url

        if element_data.mode is not None:
            # Валидация перехода режимов
            self._validate_mode_transition(element.mode, element_data.mode)
            element.mode = element_data.mode

        if element_data.retention_days is not None:
            element.retention_days = element_data.retention_days

        if element_data.max_size_gb is not None:
            element.max_size_gb = element_data.max_size_gb

        if element_data.config is not None:
            element.config = element_data.config

        element.updated_at = datetime.utcnow()

        try:
            await db.commit()
            await db.refresh(element)

            # Обновление в Redis
            self._publish_to_redis(element)

            logger.info(f"Обновлен storage element: {element.name} (ID: {element.id})")
            return element

        except Exception as e:
            await db.rollback()
            logger.error(f"Ошибка обновления storage element: {e}")
            raise ValueError("Ошибка обновления storage element")

    async def delete_storage_element(
        self,
        db: AsyncSession,
        element_id: str
    ) -> bool:
        """
        Удаляет элемент хранения.

        Args:
            db: Database session
            element_id: ID элемента

        Returns:
            True если удален, False если не найден
        """
        element = await self.get_storage_element_by_id(db, element_id)
        if not element:
            return False

        await db.delete(element)
        await db.commit()

        # Удаление из Redis
        redis_service.delete_storage_element(element_id)

        logger.info(f"Удален storage element: {element.name} (ID: {element.id})")
        return True

    async def activate_storage_element(
        self,
        db: AsyncSession,
        element_id: str
    ) -> bool:
        """
        Активирует элемент хранения.

        Args:
            db: Database session
            element_id: ID элемента

        Returns:
            True если успешно
        """
        element = await self.get_storage_element_by_id(db, element_id)
        if not element:
            return False

        element.is_active = True
        element.updated_at = datetime.utcnow()
        await db.commit()

        # Обновление в Redis
        self._publish_to_redis(element)

        logger.info(f"Активирован storage element: {element.name}")
        return True

    async def deactivate_storage_element(
        self,
        db: AsyncSession,
        element_id: str
    ) -> bool:
        """
        Деактивирует элемент хранения.

        Args:
            db: Database session
            element_id: ID элемента

        Returns:
            True если успешно
        """
        element = await self.get_storage_element_by_id(db, element_id)
        if not element:
            return False

        element.is_active = False
        element.updated_at = datetime.utcnow()
        await db.commit()

        # Обновление в Redis
        self._publish_to_redis(element)

        logger.info(f"Деактивирован storage element: {element.name}")
        return True

    async def update_storage_usage(
        self,
        db: AsyncSession,
        element_id: str,
        current_size_gb: float
    ) -> bool:
        """
        Обновляет информацию об использовании хранилища.

        Args:
            db: Database session
            element_id: ID элемента
            current_size_gb: Текущий размер в GB

        Returns:
            True если успешно
        """
        element = await self.get_storage_element_by_id(db, element_id)
        if not element:
            return False

        element.current_size_gb = current_size_gb
        element.last_checked_at = datetime.utcnow()
        element.updated_at = datetime.utcnow()
        await db.commit()

        logger.debug(f"Обновлен размер storage element {element.name}: {current_size_gb} GB")
        return True

    async def list_storage_elements(
        self,
        db: AsyncSession,
        page: int = 1,
        size: int = 20,
        search: Optional[StorageElementSearchParams] = None
    ) -> Tuple[List[StorageElement], int]:
        """
        Получает пагинированный список элементов хранения с фильтрацией.

        Args:
            db: Database session
            page: Номер страницы (начиная с 1)
            size: Размер страницы
            search: Параметры поиска и фильтрации

        Returns:
            Tuple (список элементов, общее количество)
        """
        # Базовый запрос
        query = select(StorageElement)

        # Применение фильтров
        filters = []

        if search:
            # Поиск по name, description
            if search.search:
                search_pattern = f"%{search.search}%"
                filters.append(
                    or_(
                        StorageElement.name.ilike(search_pattern),
                        StorageElement.description.ilike(search_pattern)
                    )
                )

            # Фильтр по типу хранилища
            if search.storage_type:
                filters.append(StorageElement.storage_type == search.storage_type)

            # Фильтр по режиму
            if search.mode:
                filters.append(StorageElement.mode == search.mode)

            # Фильтр по активности
            if search.is_active is not None:
                filters.append(StorageElement.is_active == search.is_active)

        # Применяем все фильтры
        if filters:
            query = query.where(and_(*filters))

        # Подсчет общего количества
        count_query = select(func.count()).select_from(StorageElement)
        if filters:
            count_query = count_query.where(and_(*filters))

        result = await db.execute(count_query)
        total = result.scalar()

        # Пагинация
        offset = (page - 1) * size
        query = query.offset(offset).limit(size)

        # Сортировка (по дате создания, новые сначала)
        query = query.order_by(StorageElement.created_at.desc())

        # Выполнение запроса
        result = await db.execute(query)
        elements = result.scalars().all()

        return list(elements), total

    async def get_storage_stats(self, db: AsyncSession) -> StorageElementStats:
        """
        Получает статистику элементов хранения.

        Args:
            db: Database session

        Returns:
            StorageElementStats с общей статистикой
        """
        # Общее количество
        total_result = await db.execute(select(func.count(StorageElement.id)))
        total_elements = total_result.scalar()

        # Активные элементы
        active_result = await db.execute(
            select(func.count(StorageElement.id)).where(StorageElement.is_active == True)
        )
        active_elements = active_result.scalar()

        # Неактивные элементы
        inactive_elements = total_elements - active_elements

        # Распределение по типам хранилища
        type_result = await db.execute(
            select(StorageElement.storage_type, func.count(StorageElement.id))
            .group_by(StorageElement.storage_type)
        )
        by_storage_type = {row[0]: row[1] for row in type_result.all()}

        # Распределение по режимам
        mode_result = await db.execute(
            select(StorageElement.mode, func.count(StorageElement.id))
            .group_by(StorageElement.mode)
        )
        by_mode = {row[0]: row[1] for row in mode_result.all()}

        # Общий используемый размер
        size_result = await db.execute(
            select(func.sum(StorageElement.current_size_gb))
        )
        total_size_gb = size_result.scalar() or 0.0

        # Общий максимальный размер
        max_size_result = await db.execute(
            select(func.sum(StorageElement.max_size_gb))
        )
        total_max_size_gb = max_size_result.scalar() or 0.0

        return StorageElementStats(
            total_elements=total_elements,
            active_elements=active_elements,
            inactive_elements=inactive_elements,
            by_storage_type=by_storage_type,
            by_mode=by_mode,
            total_size_gb=total_size_gb,
            total_max_size_gb=total_max_size_gb,
            usage_percentage=(total_size_gb / total_max_size_gb * 100) if total_max_size_gb > 0 else 0.0
        )

    def _validate_mode_transition(self, current_mode: str, new_mode: str):
        """
        Валидирует переход между режимами.

        Args:
            current_mode: Текущий режим
            new_mode: Новый режим

        Raises:
            ValueError: Если переход невалиден
        """
        # Правила переходов:
        # edit -> нельзя изменить (fixed)
        # rw -> ro
        # ro -> ar
        # ar -> нельзя изменить (требует перезапуск)

        if current_mode == "edit":
            raise ValueError("Режим 'edit' не может быть изменен через API")

        if current_mode == "ar":
            raise ValueError("Режим 'ar' не может быть изменен через API (требуется изменение конфигурации и перезапуск)")

        valid_transitions = {
            "rw": ["ro"],
            "ro": ["ar"]
        }

        allowed = valid_transitions.get(current_mode, [])
        if new_mode not in allowed:
            raise ValueError(f"Недопустимый переход режима: {current_mode} -> {new_mode}")

    def _publish_to_redis(self, element: StorageElement):
        """
        Публикует конфигурацию storage element в Redis для Service Discovery.

        Args:
            element: Storage element для публикации
        """
        try:
            config = {
                "id": element.id,
                "name": element.name,
                "description": element.description,
                "storage_type": element.storage_type,
                "base_url": element.base_url,
                "mode": element.mode,
                "retention_days": element.retention_days,
                "max_size_gb": element.max_size_gb,
                "current_size_gb": element.current_size_gb,
                "is_active": element.is_active,
                "config": element.config,
                "updated_at": element.updated_at.isoformat() if element.updated_at else None
            }

            redis_service.publish_storage_element(element.id, config)
            logger.debug(f"Опубликован storage element в Redis: {element.name}")

        except Exception as e:
            logger.error(f"Ошибка публикации в Redis для {element.name}: {e}")
            # Не поднимаем исключение, чтобы не прерывать основную операцию


# Глобальный экземпляр сервиса
storage_service = StorageService()
