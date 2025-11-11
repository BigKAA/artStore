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
from datetime import datetime
from pathlib import Path
from typing import AsyncGenerator, BinaryIO, Optional
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import FileOperationException, StorageException, WALException
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
        storage: Optional[StorageService] = None
    ):
        """
        Инициализация File Service.

        Args:
            db: Async сессия базы данных
            storage: Storage сервис (опционально, по умолчанию из settings)
        """
        self.db = db
        self.storage = storage or get_storage_service()
        self.wal = WALService(db)

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
            FileOperationException: Ошибка создания файла

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
        timestamp = datetime.utcnow()
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

            # Путь к attr.json файлу
            if settings.storage.type.value == "local":
                # Local storage: attr.json рядом с файлом
                data_file_path = Path(settings.storage.local.base_path) / relative_path
                attr_file_path = get_attr_file_path(data_file_path)
            else:
                # S3: attr.json в отдельной директории
                attr_relative_path = f"{storage_path}.attrs/{storage_filename}.attr.json"
                attr_file_path = Path(settings.storage.local.base_path) / attr_relative_path

            await write_attr_file(attr_file_path, attributes)

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
                    data_file_path = Path(settings.storage.local.base_path) / relative_path
                    attr_file_path = get_attr_file_path(data_file_path)
                else:
                    attr_relative_path = f"{storage_path}.attrs/{storage_filename}.attr.json"
                    attr_file_path = Path(settings.storage.local.base_path) / attr_relative_path

                if attr_file_path.exists():
                    await delete_attr_file(attr_file_path)
            except Exception as attr_error:
                logger.error(f"Failed to cleanup attr file: {attr_error}")

            # Удаление из DB cache
            try:
                await self.db.rollback()
            except Exception as db_error:
                logger.error(f"Failed to rollback database: {db_error}")

            raise FileOperationException(
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
            FileOperationException: Файл не найден или ошибка чтения
        """
        try:
            # Получение метаданных из DB cache
            result = await self.db.execute(
                select(FileMetadata).where(FileMetadata.file_id == file_id)
            )
            metadata = result.scalar_one_or_none()

            if not metadata:
                raise FileOperationException(
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
                    "filename": metadata.original_filename
                }
            )

        except FileOperationException:
            raise
        except Exception as e:
            logger.error(
                f"Failed to retrieve file: {e}",
                extra={
                    "file_id": str(file_id),
                    "error": str(e)
                }
            )
            raise FileOperationException(
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
            FileOperationException: Файл не найден или ошибка удаления
        """
        transaction_id = None

        try:
            # Получение метаданных
            result = await self.db.execute(
                select(FileMetadata).where(FileMetadata.file_id == file_id)
            )
            metadata = result.scalar_one_or_none()

            if not metadata:
                raise FileOperationException(
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
                data_file_path = Path(settings.storage.local.base_path) / relative_path
                attr_file_path = get_attr_file_path(data_file_path)
            else:
                attr_relative_path = f"{metadata.storage_path}.attrs/{metadata.storage_filename}.attr.json"
                attr_file_path = Path(settings.storage.local.base_path) / attr_relative_path

            if attr_file_path.exists():
                await delete_attr_file(attr_file_path)

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
                    "filename": metadata.original_filename,
                    "user_id": user_id
                }
            )

        except FileOperationException:
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

            raise FileOperationException(
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

        Args:
            file_id: UUID файла

        Returns:
            FileMetadata или None если не найден
        """
        try:
            result = await self.db.execute(
                select(FileMetadata).where(FileMetadata.file_id == file_id)
            )
            return result.scalar_one_or_none()

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
            FileOperationException: Ошибка обновления метаданных
        """
        transaction_id = None

        try:
            # Получение текущих метаданных
            result = await self.db.execute(
                select(FileMetadata).where(FileMetadata.file_id == file_id)
            )
            db_metadata = result.scalar_one_or_none()

            if not db_metadata:
                raise FileOperationException(
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

            db_metadata.updated_at = datetime.utcnow()
            await self.db.commit()

            # ШАГ 3: Обновление attr.json
            relative_path = f"{db_metadata.storage_path}{db_metadata.storage_filename}"

            if settings.storage.type.value == "local":
                data_file_path = Path(settings.storage.local.base_path) / relative_path
                attr_file_path = get_attr_file_path(data_file_path)
            else:
                attr_relative_path = f"{db_metadata.storage_path}.attrs/{db_metadata.storage_filename}.attr.json"
                attr_file_path = Path(settings.storage.local.base_path) / attr_relative_path

            # Чтение текущих атрибутов
            attributes = await read_attr_file(attr_file_path)

            # Обновление полей
            if description is not None:
                attributes.description = description
            if version is not None:
                attributes.version = version
            if metadata is not None:
                attributes.metadata = metadata

            attributes.updated_at = datetime.utcnow()

            # Запись обновленных атрибутов
            await write_attr_file(attr_file_path, attributes)

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

        except FileOperationException:
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

            raise FileOperationException(
                message="Failed to update file metadata",
                error_code="FILE_UPDATE_FAILED",
                details={"file_id": str(file_id), "error": str(e)}
            )
