"""
File Service - высокоуровневые операции с файлами.

Координация всех компонентов системы:
- WAL Service для атомарности
- Storage Service для физического хранения
- Attr Utils для метаданных
- Database Cache для быстрого поиска

Обеспечивает:
- ACID транзакции через WAL
- Consistency Protocol: WAL → Attr File → DB Cache → Commit
- Автоматический rollback при ошибках
- Полное логирование операций
"""

import io
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import AsyncGenerator, BinaryIO, Optional
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import StorageException, WALException
from app.models.file_metadata import FileMetadata
from app.models.wal import WALOperationType
from app.services.storage_service import StorageService, get_storage_service
from app.services.wal_service import WALService
from app.utils.attr_utils import (
    FileAttributes,
    delete_attr_file,
    get_attr_file_path,
    read_attr_file,
    write_attr_file,
)
from app.utils.file_naming import generate_storage_filename, generate_storage_path
from app.services.cache_lock_manager import (
    CacheLockManager,
    LockType,
    get_cache_lock_manager
)
from app.services.storage_backends import get_storage_backend

logger = logging.getLogger(__name__)


class FileService:
    """
    Высокоуровневый сервис управления файлами.

    Координирует все компоненты:
    - WAL Service
    - Storage Service (Local/S3)
    - Attribute Files
    - Database Cache

    Примеры:
        >>> file_service = FileService(db_session)
        >>> file_id = await file_service.create_file(
        ...     file_data=uploaded_file,
        ...     original_filename="report.pdf",
        ...     content_type="application/pdf",
        ...     user_id="user123",
        ...     username="ivanov"
        ... )
    """

    def __init__(
        self,
        db: AsyncSession,
        storage: Optional[StorageService] = None,
        lock_manager: Optional[CacheLockManager] = None
    ):
        """
        Инициализация File Service.

        Args:
            db: Async сессия базы данных
            storage: Storage сервис (опционально, по умолчанию из settings)
            lock_manager: Cache lock manager для lazy rebuild (опционально)
        """
        self.db = db
        self.storage = storage or get_storage_service()
        self.wal = WALService(db)
        self.lock_manager = lock_manager
        self.storage_backend = get_storage_backend()

    async def create_file(
        self,
        file_data: BinaryIO,
        original_filename: str,
        content_type: str,
        user_id: str,
        username: str,
        user_fullname: Optional[str] = None,
        description: Optional[str] = None,
        version: Optional[str] = None,
        metadata: Optional[dict] = None
    ) -> UUID:
        """
        Создать новый файл в хранилище.

        Процесс (Consistency Protocol):
        1. WAL: Начало транзакции (PENDING)
        2. Storage: Запись файла с checksum
        3. Attr File: Запись *.attr.json (источник истины)
        4. DB Cache: Сохранение метаданных для поиска
        5. WAL: Коммит транзакции (COMMITTED)

        При любой ошибке:
        - Автоматический rollback через WAL
        - Удаление созданных файлов
        - Очистка DB cache

        Args:
            file_data: Бинарные данные файла
            original_filename: Оригинальное имя файла
            content_type: MIME type
            user_id: User ID создателя
            username: Username создателя
            user_fullname: ФИО создателя (опционально)
            description: Описание содержимого (опционально)
            version: Версия документа (опционально)
            metadata: Дополнительные метаданные (опционально)

        Returns:
            UUID: file_id созданного файла

        Raises:
            StorageException: Ошибка создания файла

        Примеры:
            >>> with open("document.pdf", "rb") as f:
            ...     file_id = await file_service.create_file(
            ...         file_data=f,
            ...         original_filename="document.pdf",
            ...         content_type="application/pdf",
            ...         user_id="user123",
            ...         username="ivanov",
            ...         user_fullname="Иван Иванов",
            ...         description="Quarterly report"
            ...     )
        """
        file_id = uuid4()
        timestamp = datetime.now(timezone.utc)
        transaction_id = None

        # Генерация имен и путей
        storage_filename = generate_storage_filename(
            original_filename=original_filename,
            username=username,
            timestamp=timestamp,
            file_uuid=file_id
        )
        storage_path = generate_storage_path(timestamp)
        relative_path = f"{storage_path}{storage_filename}"

        try:
            # ШАГ 1: Начало WAL транзакции
            transaction_id = await self.wal.start_transaction(
                operation_type=WALOperationType.FILE_CREATE,
                file_id=file_id,
                operation_data={
                    "original_filename": original_filename,
                    "storage_filename": storage_filename,
                    "storage_path": storage_path,
                    "relative_path": relative_path,
                    "content_type": content_type
                },
                user_id=user_id
            )

            # ШАГ 2: Запись файла в storage с вычислением checksum
            file_size, checksum = await self.storage.write_file(
                relative_path=relative_path,
                file_data=file_data
            )

            # ШАГ 3: Создание и запись attr.json файла (источник истины)
            attributes = FileAttributes(
                file_id=file_id,
                original_filename=original_filename,
                storage_filename=storage_filename,
                file_size=file_size,
                content_type=content_type,
                created_at=timestamp,
                updated_at=timestamp,
                created_by_id=user_id,
                created_by_username=username,
                created_by_fullname=user_fullname,
                description=description,
                version=version,
                storage_path=storage_path,
                checksum=checksum,
                metadata=metadata or {}
            )

            # ШАГ 3: Создание и запись attr.json файла
            if settings.storage.type.value == "local":
                # Local storage: attr.json рядом с файлом (локально)
                data_file_path = Path(settings.storage.local.base_path) / relative_path
                attr_file_path = get_attr_file_path(data_file_path)
                await write_attr_file(attr_file_path, attributes)
            else:
                # S3: attr.json в S3 рядом с файлом данных
                # Формат: storage_element_01/2025/11/25/16/file.pdf.attr.json
                attr_relative_path = f"{relative_path}.attr.json"
                await self.storage.write_attr_file(attr_relative_path, attributes.model_dump())

            # ШАГ 4: Сохранение в DB cache для быстрого поиска
            db_metadata = FileMetadata(
                file_id=file_id,
                original_filename=original_filename,
                storage_filename=storage_filename,
                file_size=file_size,
                content_type=content_type,
                created_at=timestamp,
                updated_at=timestamp,
                created_by_id=user_id,
                created_by_username=username,
                created_by_fullname=user_fullname,
                description=description,
                version=version,
                storage_path=storage_path,
                checksum=checksum,
                metadata_json=metadata
            )

            self.db.add(db_metadata)
            await self.db.commit()

            # ШАГ 5: Коммит WAL транзакции
            await self.wal.commit(
                transaction_id,
                result_data={
                    "file_id": str(file_id),
                    "checksum": checksum,
                    "file_size": file_size
                }
            )

            logger.info(
                "File created successfully",
                extra={
                    "file_id": str(file_id),
                    "original_filename": original_filename,
                    "file_size": file_size,
                    "checksum": checksum,
                    "user_id": user_id
                }
            )

            return file_id

        except Exception as e:
            # Rollback: Очистка всех созданных ресурсов
            logger.error(
                f"Failed to create file, rolling back: {e}",
                extra={
                    "file_id": str(file_id),
                    "original_filename": original_filename,
                    "error": str(e)
                }
            )

            # WAL Rollback
            if transaction_id:
                try:
                    await self.wal.rollback(transaction_id, str(e))
                except Exception as wal_error:
                    logger.error(f"WAL rollback failed: {wal_error}")

            # Удаление файла из storage
            try:
                if await self.storage.file_exists(relative_path):
                    await self.storage.delete_file(relative_path)
            except Exception as storage_error:
                logger.error(f"Failed to cleanup storage file: {storage_error}")

            # Удаление attr.json
            try:
                if settings.storage.type.value == "local":
                    # Local storage: удаление локального attr.json
                    data_file_path = Path(settings.storage.local.base_path) / relative_path
                    attr_file_path = get_attr_file_path(data_file_path)
                    if attr_file_path.exists():
                        await delete_attr_file(attr_file_path)
                else:
                    # S3: удаление attr.json из S3
                    attr_relative_path = f"{relative_path}.attr.json"
                    await self.storage.delete_attr_file(attr_relative_path)
            except Exception as attr_error:
                logger.error(f"Failed to cleanup attr file: {attr_error}")

            # Удаление из DB cache
            try:
                await self.db.rollback()
            except Exception as db_error:
                logger.error(f"Failed to rollback database: {db_error}")

            raise StorageException(
                message="Failed to create file",
                error_code="FILE_CREATE_FAILED",
                details={
                    "file_id": str(file_id),
                    "original_filename": original_filename,
                    "error": str(e)
                }
            )

    async def get_file(
        self,
        file_id: UUID
    ) -> AsyncGenerator[bytes, None]:
        """
        Получить файл для скачивания (streaming).

        Args:
            file_id: UUID файла

        Yields:
            bytes: Chunk данных файла

        Raises:
            StorageException: Файл не найден или ошибка чтения
        """
        try:
            # Получение метаданных из DB cache
            result = await self.db.execute(
                select(FileMetadata).where(FileMetadata.file_id == file_id)
            )
            metadata = result.scalar_one_or_none()

            if not metadata:
                raise StorageException(
                    message=f"File not found: {file_id}",
                    error_code="FILE_NOT_FOUND",
                    details={"file_id": str(file_id)}
                )

            # Формирование относительного пути
            relative_path = f"{metadata.storage_path}{metadata.storage_filename}"

            # Streaming read из storage
            async for chunk in self.storage.read_file(relative_path):
                yield chunk

            logger.info(
                "File retrieved successfully",
                extra={
                    "file_id": str(file_id),
                    "original_filename": metadata.original_filename
                }
            )

        except StorageException:
            raise
        except Exception as e:
            logger.error(
                f"Failed to retrieve file: {e}",
                extra={
                    "file_id": str(file_id),
                    "error": str(e)
                }
            )
            raise StorageException(
                message="Failed to retrieve file",
                error_code="FILE_RETRIEVE_FAILED",
                details={"file_id": str(file_id), "error": str(e)}
            )

    async def delete_file(
        self,
        file_id: UUID,
        user_id: str
    ) -> None:
        """
        Удалить файл из хранилища (только edit mode).

        Процесс:
        1. WAL: Начало транзакции (PENDING)
        2. Storage: Удаление файла
        3. Attr File: Удаление *.attr.json
        4. DB Cache: Удаление метаданных
        5. WAL: Коммит транзакции (COMMITTED)

        Args:
            file_id: UUID файла
            user_id: User ID инициатора удаления

        Raises:
            StorageException: Файл не найден или ошибка удаления
        """
        transaction_id = None

        try:
            # Получение метаданных
            result = await self.db.execute(
                select(FileMetadata).where(FileMetadata.file_id == file_id)
            )
            metadata = result.scalar_one_or_none()

            if not metadata:
                raise StorageException(
                    message=f"File not found: {file_id}",
                    error_code="FILE_NOT_FOUND",
                    details={"file_id": str(file_id)}
                )

            relative_path = f"{metadata.storage_path}{metadata.storage_filename}"

            # ШАГ 1: Начало WAL транзакции
            transaction_id = await self.wal.start_transaction(
                operation_type=WALOperationType.FILE_DELETE,
                file_id=file_id,
                operation_data={
                    "original_filename": metadata.original_filename,
                    "storage_filename": metadata.storage_filename,
                    "relative_path": relative_path
                },
                user_id=user_id
            )

            # ШАГ 2: Удаление файла из storage
            await self.storage.delete_file(relative_path)

            # ШАГ 3: Удаление attr.json
            if settings.storage.type.value == "local":
                # Local storage: удаление локального attr.json
                data_file_path = Path(settings.storage.local.base_path) / relative_path
                attr_file_path = get_attr_file_path(data_file_path)
                if attr_file_path.exists():
                    await delete_attr_file(attr_file_path)
            else:
                # S3: удаление attr.json из S3
                attr_relative_path = f"{relative_path}.attr.json"
                await self.storage.delete_attr_file(attr_relative_path)

            # ШАГ 4: Удаление из DB cache
            await self.db.delete(metadata)
            await self.db.commit()

            # ШАГ 5: Коммит WAL транзакции
            await self.wal.commit(
                transaction_id,
                result_data={"file_id": str(file_id)}
            )

            logger.info(
                "File deleted successfully",
                extra={
                    "file_id": str(file_id),
                    "original_filename": metadata.original_filename,
                    "user_id": user_id
                }
            )

        except StorageException:
            # Rollback WAL
            if transaction_id:
                try:
                    await self.wal.rollback(transaction_id, str(e))
                except Exception as wal_error:
                    logger.error(f"WAL rollback failed: {wal_error}")
            raise

        except Exception as e:
            logger.error(
                f"Failed to delete file: {e}",
                extra={
                    "file_id": str(file_id),
                    "error": str(e)
                }
            )

            # Rollback WAL
            if transaction_id:
                try:
                    await self.wal.rollback(transaction_id, str(e))
                except Exception as wal_error:
                    logger.error(f"WAL rollback failed: {wal_error}")

            raise StorageException(
                message="Failed to delete file",
                error_code="FILE_DELETE_FAILED",
                details={"file_id": str(file_id), "error": str(e)}
            )

    async def get_file_metadata(
        self,
        file_id: UUID
    ) -> Optional[FileMetadata]:
        """
        Получить метаданные файла из DB cache.

        PHASE 4: Lazy Rebuild Integration
        - Проверяет TTL кеша через property cache_expired
        - При expired entry автоматически пересобирает из attr.json
        - Использует LAZY_REBUILD lock (низкий приоритет)

        Args:
            file_id: UUID файла

        Returns:
            FileMetadata или None если не найден
        """
        try:
            result = await self.db.execute(
                select(FileMetadata).where(FileMetadata.file_id == file_id)
            )
            metadata = result.scalar_one_or_none()

            # Если не найден в cache - вернуть None
            if not metadata:
                return None

            # PHASE 4: Проверка TTL и lazy rebuild если expired
            if metadata.cache_expired:
                logger.info(
                    "Cache entry expired, triggering lazy rebuild",
                    extra={
                        "file_id": str(file_id),
                        "cache_updated_at": metadata.cache_updated_at.isoformat(),
                        "cache_ttl_hours": metadata.cache_ttl_hours
                    }
                )

                # Попытка rebuild из attr.json (non-blocking)
                try:
                    refreshed_metadata = await self._rebuild_entry_from_attr(file_id)

                    if refreshed_metadata:
                        logger.info(
                            "Cache entry rebuilt successfully from attr.json",
                            extra={"file_id": str(file_id)}
                        )
                        return refreshed_metadata
                    else:
                        # Rebuild не удался, но возвращаем старый cache (graceful degradation)
                        logger.warning(
                            "Failed to rebuild cache entry, returning stale data",
                            extra={"file_id": str(file_id)}
                        )
                        return metadata

                except Exception as e:
                    # Ошибка rebuild - возвращаем старый cache (graceful degradation)
                    logger.error(
                        f"Error during lazy rebuild: {e}",
                        extra={
                            "file_id": str(file_id),
                            "error": str(e)
                        }
                    )
                    return metadata

            # Cache не expired - вернуть как есть
            return metadata

        except Exception as e:
            logger.error(
                f"Failed to get file metadata: {e}",
                extra={
                    "file_id": str(file_id),
                    "error": str(e)
                }
            )
            return None

    async def update_file_metadata(
        self,
        file_id: UUID,
        user_id: str,
        description: Optional[str] = None,
        version: Optional[str] = None,
        metadata: Optional[dict] = None
    ) -> None:
        """
        Обновить метаданные файла.

        Процесс:
        1. WAL: Начало транзакции
        2. DB Cache: Обновление метаданных
        3. Attr File: Обновление *.attr.json
        4. WAL: Коммит

        Args:
            file_id: UUID файла
            user_id: User ID инициатора обновления
            description: Новое описание (опционально)
            version: Новая версия (опционально)
            metadata: Новые дополнительные метаданные (опционально)

        Raises:
            StorageException: Ошибка обновления метаданных
        """
        transaction_id = None

        try:
            # Получение текущих метаданных
            result = await self.db.execute(
                select(FileMetadata).where(FileMetadata.file_id == file_id)
            )
            db_metadata = result.scalar_one_or_none()

            if not db_metadata:
                raise StorageException(
                    message=f"File not found: {file_id}",
                    error_code="FILE_NOT_FOUND",
                    details={"file_id": str(file_id)}
                )

            # ШАГ 1: Начало WAL транзакции
            transaction_id = await self.wal.start_transaction(
                operation_type=WALOperationType.FILE_UPDATE,
                file_id=file_id,
                operation_data={
                    "description": description,
                    "version": version,
                    "metadata": metadata
                },
                user_id=user_id
            )

            # ШАГ 2: Обновление DB cache
            if description is not None:
                db_metadata.description = description
            if version is not None:
                db_metadata.version = version
            if metadata is not None:
                db_metadata.metadata_json = metadata

            db_metadata.updated_at = datetime.now(timezone.utc)
            await self.db.commit()

            # ШАГ 3: Обновление attr.json
            relative_path = f"{db_metadata.storage_path}{db_metadata.storage_filename}"

            if settings.storage.type.value == "local":
                # Local storage: чтение и запись локального attr.json
                data_file_path = Path(settings.storage.local.base_path) / relative_path
                attr_file_path = get_attr_file_path(data_file_path)

                # Чтение текущих атрибутов
                attributes = await read_attr_file(attr_file_path)

                # Обновление полей
                if description is not None:
                    attributes.description = description
                if version is not None:
                    attributes.version = version
                if metadata is not None:
                    attributes.metadata = metadata

                attributes.updated_at = datetime.now(timezone.utc)

                # Запись обновленных атрибутов
                await write_attr_file(attr_file_path, attributes)
            else:
                # S3: чтение и запись attr.json в S3
                attr_relative_path = f"{relative_path}.attr.json"

                # Чтение текущих атрибутов из S3
                attributes_dict = await self.storage.read_attr_file(attr_relative_path)

                # Обновление полей
                if description is not None:
                    attributes_dict['description'] = description
                if version is not None:
                    attributes_dict['version'] = version
                if metadata is not None:
                    attributes_dict['metadata'] = metadata

                attributes_dict['updated_at'] = datetime.now(timezone.utc).isoformat()

                # Запись обновленных атрибутов в S3
                await self.storage.write_attr_file(attr_relative_path, attributes_dict)

            # ШАГ 4: Коммит WAL транзакции
            await self.wal.commit(
                transaction_id,
                result_data={"file_id": str(file_id)}
            )

            logger.info(
                "File metadata updated successfully",
                extra={
                    "file_id": str(file_id),
                    "user_id": user_id
                }
            )

        except StorageException:
            # Rollback WAL
            if transaction_id:
                try:
                    await self.wal.rollback(transaction_id, str(e))
                except Exception as wal_error:
                    logger.error(f"WAL rollback failed: {wal_error}")
            raise

        except Exception as e:
            logger.error(
                f"Failed to update file metadata: {e}",
                extra={
                    "file_id": str(file_id),
                    "error": str(e)
                }
            )

            # Rollback WAL и DB
            if transaction_id:
                try:
                    await self.wal.rollback(transaction_id, str(e))
                except Exception as wal_error:
                    logger.error(f"WAL rollback failed: {wal_error}")

            try:
                await self.db.rollback()
            except Exception as db_error:
                logger.error(f"DB rollback failed: {db_error}")

            raise StorageException(
                message="Failed to update file metadata",
                error_code="FILE_UPDATE_FAILED",
                details={"file_id": str(file_id), "error": str(e)}
            )

    async def _get_lock_manager(self) -> CacheLockManager:
        """
        Получить lock manager (lazy initialization).

        Returns:
            CacheLockManager: Singleton instance
        """
        if not self.lock_manager:
            self.lock_manager = await get_cache_lock_manager()
        return self.lock_manager

    async def _rebuild_entry_from_attr(
        self,
        file_id: UUID
    ) -> Optional[FileMetadata]:
        """
        Пересобрать cache entry из attr.json файла.

        PHASE 4: Lazy Rebuild Implementation
        - Использует LAZY_REBUILD lock (низкий приоритет)
        - Если MANUAL_REBUILD lock занят - пропускает rebuild (graceful degradation)
        - Читает attr.json через StorageBackend abstraction
        - Обновляет DB cache с новым cache_updated_at timestamp

        Args:
            file_id: UUID файла для rebuild

        Returns:
            FileMetadata: Обновленные метаданные или None если не удалось

        Raises:
            Не генерирует исключения - graceful degradation при ошибках
        """
        lock_mgr = await self._get_lock_manager()

        try:
            # Попытка захватить LAZY_REBUILD lock (non-blocking)
            acquired = await lock_mgr.acquire_lock(
                LockType.LAZY_REBUILD,
                timeout=30,  # 30 секунд для lazy rebuild
                blocking=False  # Non-blocking - если занято, skip
            )

            if not acquired:
                # Lock занят (вероятно MANUAL_REBUILD) - пропускаем
                logger.info(
                    "Cannot acquire LAZY_REBUILD lock, skipping rebuild",
                    extra={
                        "file_id": str(file_id),
                        "reason": "Higher priority operation in progress"
                    }
                )
                return None

            try:
                # Получить текущие метаданные из cache
                result = await self.db.execute(
                    select(FileMetadata).where(FileMetadata.file_id == file_id)
                )
                current_metadata = result.scalar_one_or_none()

                if not current_metadata:
                    logger.warning(
                        "Cache entry not found for rebuild",
                        extra={"file_id": str(file_id)}
                    )
                    return None

                # Построить путь к attr.json файлу
                relative_path = f"{current_metadata.storage_path}{current_metadata.storage_filename}"
                attr_relative_path = f"{relative_path}.attr.json"

                # Прочитать attr.json через StorageBackend
                try:
                    attributes = await self.storage_backend.read_attr_file(attr_relative_path)
                except FileNotFoundError:
                    logger.warning(
                        "Attr file not found for rebuild",
                        extra={
                            "file_id": str(file_id),
                            "attr_path": attr_relative_path
                        }
                    )
                    return None

                # Обновить метаданные из attr.json
                current_metadata.original_filename = attributes.get('original_filename', current_metadata.original_filename)
                current_metadata.file_size = attributes.get('file_size', current_metadata.file_size)
                current_metadata.content_type = attributes.get('mime_type', current_metadata.content_type)
                current_metadata.description = attributes.get('description', current_metadata.description)
                current_metadata.version = str(attributes.get('version', current_metadata.version))
                current_metadata.checksum = attributes.get('sha256', current_metadata.checksum)
                current_metadata.metadata = attributes

                # Обновить timestamps
                if 'created_at' in attributes:
                    current_metadata.created_at = datetime.fromisoformat(
                        attributes['created_at'].replace('Z', '+00:00')
                    )
                if 'updated_at' in attributes:
                    current_metadata.updated_at = datetime.fromisoformat(
                        attributes['updated_at'].replace('Z', '+00:00')
                    )

                # КРИТИЧНО: Обновить cache timestamps
                current_metadata.cache_updated_at = datetime.now(timezone.utc)

                # Определить TTL в зависимости от режима
                mode = settings.app.mode.value
                current_metadata.cache_ttl_hours = 168 if mode in ['ro', 'ar'] else 24

                # Сохранить в DB
                await self.db.commit()

                logger.info(
                    "Cache entry rebuilt successfully from attr.json",
                    extra={
                        "file_id": str(file_id),
                        "new_cache_ttl_hours": current_metadata.cache_ttl_hours
                    }
                )

                return current_metadata

            finally:
                # Всегда освобождать lock
                await lock_mgr.release_lock(LockType.LAZY_REBUILD)

        except Exception as e:
            logger.error(
                f"Failed to rebuild cache entry from attr.json: {e}",
                extra={
                    "file_id": str(file_id),
                    "error": str(e)
                }
            )
            return None
