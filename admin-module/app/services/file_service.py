"""
Admin Module - File Registry Service.

Sprint 15.2: Бизнес-логика для управления file registry.

Сервис отвечает за:
- Регистрацию новых файлов при upload через Ingester Module
- Получение метаданных файла
- Обновление файла при финализации (temporary → permanent)
- Soft delete файлов
- Pagination и фильтрация файлов

ВАЖНО:
- Все операции асинхронные (asyncpg через SQLAlchemy)
- Transaction safety для consistency
- Audit logging для всех критических операций
"""

import logging
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import select, func, update, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.models.file import File, RetentionPolicy
from app.schemas.file import (
    FileRegisterRequest,
    FileUpdateRequest,
    FileResponse,
    FileListResponse,
    FileDeleteResponse,
)

logger = logging.getLogger(__name__)


class FileService:
    """
    Сервис для управления file registry.

    Sprint 15.2: CRUD операции для централизованного реестра файлов.

    Usage:
        service = FileService()
        file = await service.register_file(db, request)
    """

    async def register_file(
        self,
        db: AsyncSession,
        request: FileRegisterRequest,
    ) -> FileResponse:
        """
        Регистрация нового файла в file registry.

        Вызывается Ingester Module после успешной загрузки файла в Storage Element.

        Args:
            db: AsyncSession для database операций
            request: Данные файла для регистрации

        Returns:
            FileResponse: Зарегистрированный файл

        Raises:
            ValueError: Файл с таким file_id уже существует
            SQLAlchemyError: Database errors
        """
        logger.info(
            "Registering new file in registry",
            extra={
                "file_id": str(request.file_id),
                "original_filename": request.original_filename,
                "retention_policy": request.retention_policy.value,
                "storage_element_id": request.storage_element_id
            }
        )

        # Проверка что файл с таким ID не существует
        existing_file = await self.get_file_by_id(db, request.file_id)
        if existing_file:
            logger.warning(
                "File with this ID already exists",
                extra={"file_id": str(request.file_id)}
            )
            raise ValueError(f"File with ID {request.file_id} already exists")

        # Создание новой записи
        file = File(
            file_id=request.file_id,
            original_filename=request.original_filename,
            storage_filename=request.storage_filename,
            file_size=request.file_size,
            checksum_sha256=request.checksum_sha256,
            content_type=request.content_type,
            description=request.description,
            retention_policy=request.retention_policy,
            ttl_expires_at=request.ttl_expires_at,
            ttl_days=request.ttl_days,
            storage_element_id=request.storage_element_id,
            storage_path=request.storage_path,
            compressed=request.compressed,
            compression_algorithm=request.compression_algorithm,
            original_size=request.original_size,
            uploaded_by=request.uploaded_by,
            upload_source_ip=request.upload_source_ip,
            user_metadata=request.user_metadata or {},
        )

        try:
            db.add(file)
            await db.commit()
            await db.refresh(file)

            logger.info(
                "File registered successfully",
                extra={
                    "file_id": str(file.file_id),
                    "original_filename": file.original_filename,
                    "retention_policy": file.retention_policy.value
                }
            )

            return self._to_response(file)

        except IntegrityError as e:
            await db.rollback()
            logger.error(
                "Database integrity error during file registration",
                extra={
                    "file_id": str(request.file_id),
                    "error": str(e)
                }
            )
            raise ValueError(f"Failed to register file: {str(e)}")

        except SQLAlchemyError as e:
            await db.rollback()
            logger.error(
                "Database error during file registration",
                extra={
                    "file_id": str(request.file_id),
                    "error": str(e)
                },
                exc_info=True
            )
            raise

    async def get_file_by_id(
        self,
        db: AsyncSession,
        file_id: UUID,
        include_deleted: bool = False
    ) -> Optional[FileResponse]:
        """
        Получение файла по ID.

        Args:
            db: AsyncSession
            file_id: UUID файла
            include_deleted: Включать ли удаленные файлы

        Returns:
            FileResponse или None если файл не найден
        """
        logger.debug(
            "Fetching file by ID",
            extra={"file_id": str(file_id), "include_deleted": include_deleted}
        )

        query = select(File).where(File.file_id == file_id)

        if not include_deleted:
            query = query.where(File.deleted_at.is_(None))

        result = await db.execute(query)
        file = result.scalar_one_or_none()

        if file:
            return self._to_response(file)

        logger.debug(
            "File not found",
            extra={"file_id": str(file_id)}
        )
        return None

    async def update_file(
        self,
        db: AsyncSession,
        file_id: UUID,
        request: FileUpdateRequest
    ) -> Optional[FileResponse]:
        """
        Обновление файла (используется при финализации).

        Sprint 15.2: Обновляет retention_policy, storage_element_id, finalized_at.

        Args:
            db: AsyncSession
            file_id: UUID файла
            request: Данные для обновления

        Returns:
            FileResponse или None если файл не найден

        Raises:
            ValueError: Попытка некорректного обновления
            SQLAlchemyError: Database errors
        """
        logger.info(
            "Updating file metadata",
            extra={
                "file_id": str(file_id),
                "retention_policy": request.retention_policy.value if request.retention_policy else None,
                "storage_element_id": request.storage_element_id
            }
        )

        # Получить текущий файл
        file = await db.get(File, file_id)
        if not file:
            logger.warning(
                "File not found for update",
                extra={"file_id": str(file_id)}
            )
            return None

        # Валидация: нельзя менять permanent → temporary
        if request.retention_policy:
            if (file.retention_policy == RetentionPolicy.PERMANENT and
                    request.retention_policy == RetentionPolicy.TEMPORARY):
                raise ValueError(
                    "Cannot change retention_policy from permanent to temporary"
                )

        # Применение обновлений
        if request.retention_policy:
            file.retention_policy = request.retention_policy

            # При финализации temporary → permanent: очистить TTL
            if request.retention_policy == RetentionPolicy.PERMANENT:
                file.ttl_expires_at = None
                file.ttl_days = None

        if request.storage_element_id:
            file.storage_element_id = request.storage_element_id

        if request.storage_path:
            file.storage_path = request.storage_path

        if request.finalized_at:
            file.finalized_at = request.finalized_at

        if request.description is not None:
            file.description = request.description

        if request.user_metadata is not None:
            file.user_metadata = request.user_metadata

        try:
            await db.commit()
            await db.refresh(file)

            logger.info(
                "File updated successfully",
                extra={
                    "file_id": str(file.file_id),
                    "retention_policy": file.retention_policy.value,
                    "finalized": file.is_finalized
                }
            )

            return self._to_response(file)

        except SQLAlchemyError as e:
            await db.rollback()
            logger.error(
                "Database error during file update",
                extra={
                    "file_id": str(file_id),
                    "error": str(e)
                },
                exc_info=True
            )
            raise

    async def delete_file(
        self,
        db: AsyncSession,
        file_id: UUID,
        deletion_reason: str = "manual"
    ) -> Optional[FileDeleteResponse]:
        """
        Soft delete файла.

        ВАЖНО: Физическое удаление файла из Storage Element
        должно выполняться отдельно через Garbage Collector.

        Args:
            db: AsyncSession
            file_id: UUID файла
            deletion_reason: Причина удаления (manual, ttl_expired, gc_cleanup, finalized)

        Returns:
            FileDeleteResponse или None если файл не найден

        Raises:
            SQLAlchemyError: Database errors
        """
        logger.info(
            "Soft deleting file",
            extra={
                "file_id": str(file_id),
                "deletion_reason": deletion_reason
            }
        )

        file = await db.get(File, file_id)
        if not file:
            logger.warning(
                "File not found for deletion",
                extra={"file_id": str(file_id)}
            )
            return None

        # Проверка что файл не был уже удален
        if file.is_deleted:
            logger.warning(
                "File already deleted",
                extra={"file_id": str(file_id), "deleted_at": str(file.deleted_at)}
            )
            return FileDeleteResponse(
                file_id=file.file_id,
                deleted_at=file.deleted_at,
                deletion_reason=file.deletion_reason or deletion_reason,
                message="File was already deleted"
            )

        # Soft delete
        deleted_at = datetime.now(timezone.utc)
        file.deleted_at = deleted_at
        file.deletion_reason = deletion_reason

        try:
            await db.commit()
            await db.refresh(file)

            logger.info(
                "File soft deleted successfully",
                extra={
                    "file_id": str(file.file_id),
                    "deleted_at": str(deleted_at),
                    "deletion_reason": deletion_reason
                }
            )

            return FileDeleteResponse(
                file_id=file.file_id,
                deleted_at=deleted_at,
                deletion_reason=deletion_reason,
                message="File marked as deleted successfully"
            )

        except SQLAlchemyError as e:
            await db.rollback()
            logger.error(
                "Database error during file deletion",
                extra={
                    "file_id": str(file_id),
                    "error": str(e)
                },
                exc_info=True
            )
            raise

    async def list_files(
        self,
        db: AsyncSession,
        page: int = 1,
        page_size: int = 50,
        retention_policy: Optional[RetentionPolicy] = None,
        storage_element_id: Optional[str] = None,
        include_deleted: bool = False
    ) -> FileListResponse:
        """
        Получение списка файлов с pagination и фильтрацией.

        Args:
            db: AsyncSession
            page: Номер страницы (1-based)
            page_size: Размер страницы (max 1000)
            retention_policy: Фильтр по retention policy
            storage_element_id: Фильтр по storage element
            include_deleted: Включать ли удаленные файлы

        Returns:
            FileListResponse: Список файлов с метаданными pagination
        """
        logger.debug(
            "Listing files with filters",
            extra={
                "page": page,
                "page_size": page_size,
                "retention_policy": retention_policy.value if retention_policy else None,
                "storage_element_id": storage_element_id,
                "include_deleted": include_deleted
            }
        )

        # Валидация параметров
        page = max(1, page)
        page_size = min(1000, max(1, page_size))

        # Построение запроса
        query = select(File)
        count_query = select(func.count()).select_from(File)

        # Фильтры
        filters = []
        if not include_deleted:
            filters.append(File.deleted_at.is_(None))
        if retention_policy:
            filters.append(File.retention_policy == retention_policy)
        if storage_element_id:
            filters.append(File.storage_element_id == storage_element_id)

        if filters:
            query = query.where(and_(*filters))
            count_query = count_query.where(and_(*filters))

        # Подсчет total
        total_result = await db.execute(count_query)
        total = total_result.scalar_one()

        # Pagination
        offset = (page - 1) * page_size
        query = query.offset(offset).limit(page_size)

        # Сортировка: новые файлы первыми
        query = query.order_by(File.created_at.desc())

        # Выполнение запроса
        result = await db.execute(query)
        files = result.scalars().all()

        # Расчет total_pages
        total_pages = (total + page_size - 1) // page_size if total > 0 else 0

        logger.info(
            "Files list retrieved",
            extra={
                "total": total,
                "page": page,
                "page_size": page_size,
                "returned_count": len(files)
            }
        )

        return FileListResponse(
            files=[self._to_response(f) for f in files],
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages
        )

    def _to_response(self, file: File) -> FileResponse:
        """
        Конвертация File model в FileResponse schema.

        Args:
            file: File model instance

        Returns:
            FileResponse: Pydantic schema для API response
        """
        return FileResponse(
            file_id=file.file_id,
            original_filename=file.original_filename,
            storage_filename=file.storage_filename,
            file_size=file.file_size,
            checksum_sha256=file.checksum_sha256,
            content_type=file.content_type,
            description=file.description,
            retention_policy=file.retention_policy,
            ttl_expires_at=file.ttl_expires_at,
            ttl_days=file.ttl_days,
            finalized_at=file.finalized_at,
            storage_element_id=file.storage_element_id,
            storage_path=file.storage_path,
            compressed=file.compressed,
            compression_algorithm=file.compression_algorithm,
            original_size=file.original_size,
            uploaded_by=file.uploaded_by,
            upload_source_ip=file.upload_source_ip,
            user_metadata=file.user_metadata,
            created_at=file.created_at,
            updated_at=file.updated_at,
            deleted_at=file.deleted_at,
            deletion_reason=file.deletion_reason,
            is_deleted=file.is_deleted,
            is_finalized=file.is_finalized,
            is_temporary=file.is_temporary,
        )


# Singleton instance для dependency injection
_file_service: Optional[FileService] = None


def get_file_service() -> FileService:
    """
    Получение singleton instance FileService.

    Returns:
        FileService: Singleton instance
    """
    global _file_service
    if _file_service is None:
        _file_service = FileService()
    return _file_service
