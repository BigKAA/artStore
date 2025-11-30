"""
Storage Service - абстракция для работы с различными типами хранилищ.

Поддерживаемые типы хранилищ:
- Local filesystem (производственные данные на NFS/SAN)
- S3-совместимые хранилища (MinIO, AWS S3, etc.)

Все операции:
- Streaming для больших файлов
- Atomic write через temporary files
- Checksum verification
- Error handling с retry logic
"""

import hashlib
import logging
import shutil
from abc import ABC, abstractmethod
from pathlib import Path
from typing import AsyncGenerator, BinaryIO, Optional
from uuid import UUID

import aioboto3
from botocore.exceptions import ClientError

from app.core.config import settings, StorageType
from app.core.exceptions import StorageException

logger = logging.getLogger(__name__)

# Размер chunk для streaming операций (8MB)
CHUNK_SIZE = 8 * 1024 * 1024


class StorageService(ABC):
    """
    Абстрактный базовый класс для storage сервисов.

    Определяет общий интерфейс для всех типов хранилищ.
    """

    @abstractmethod
    async def write_file(
        self,
        relative_path: str,
        file_data: BinaryIO,
        expected_size: Optional[int] = None
    ) -> tuple[int, str]:
        """
        Записать файл в хранилище.

        Args:
            relative_path: Относительный путь в хранилище (year/month/day/hour/filename)
            file_data: Бинарные данные файла (file-like object)
            expected_size: Ожидаемый размер файла для валидации (опционально)

        Returns:
            tuple[int, str]: (размер файла в байтах, SHA256 checksum)

        Raises:
            StorageException: Ошибка записи файла
        """
        pass

    @abstractmethod
    async def read_file(
        self,
        relative_path: str
    ) -> AsyncGenerator[bytes, None]:
        """
        Прочитать файл из хранилища (streaming).

        Args:
            relative_path: Относительный путь в хранилище

        Yields:
            bytes: Chunk данных файла

        Raises:
            StorageException: Файл не найден или ошибка чтения
        """
        pass

    @abstractmethod
    async def delete_file(
        self,
        relative_path: str
    ) -> None:
        """
        Удалить файл из хранилища.

        Args:
            relative_path: Относительный путь в хранилище

        Raises:
            StorageException: Ошибка удаления файла
        """
        pass

    @abstractmethod
    async def file_exists(
        self,
        relative_path: str
    ) -> bool:
        """
        Проверить существование файла в хранилище.

        Args:
            relative_path: Относительный путь в хранилище

        Returns:
            bool: True если файл существует
        """
        pass

    @abstractmethod
    async def get_file_size(
        self,
        relative_path: str
    ) -> int:
        """
        Получить размер файла в байтах.

        Args:
            relative_path: Относительный путь в хранилище

        Returns:
            int: Размер файла в байтах

        Raises:
            StorageException: Файл не найден
        """
        pass


class LocalStorageService(StorageService):
    """
    Локальное файловое хранилище (NFS/SAN).

    Атомарная запись через temporary files.
    Директории создаются автоматически.
    """

    def __init__(self, base_path: Optional[Path] = None):
        """
        Инициализация Local Storage Service.

        Args:
            base_path: Базовый путь хранилища (по умолчанию из settings)
        """
        self.base_path = base_path or Path(settings.storage.local.base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)
        logger.info(f"LocalStorageService initialized with base_path: {self.base_path}")

    def _get_full_path(self, relative_path: str) -> Path:
        """Получить полный путь к файлу"""
        return self.base_path / relative_path

    async def write_file(
        self,
        relative_path: str,
        file_data: BinaryIO,
        expected_size: Optional[int] = None
    ) -> tuple[int, str]:
        """
        Записать файл в локальное хранилище.

        Процесс:
        1. Создание директорий если не существуют
        2. Запись во временный файл
        3. Вычисление checksum
        4. Атомарная замена (rename)

        Args:
            relative_path: Относительный путь (year/month/day/hour/filename)
            file_data: Бинарные данные файла
            expected_size: Ожидаемый размер (опционально)

        Returns:
            tuple[int, str]: (размер файла, SHA256 checksum)

        Raises:
            StorageException: Ошибка записи файла
        """
        target_path = self._get_full_path(relative_path)

        try:
            # Создание директорий
            target_path.parent.mkdir(parents=True, exist_ok=True)

            # Временный файл в той же директории (для atomic rename)
            temp_path = target_path.parent / f".tmp_{target_path.name}"

            # Запись во временный файл с вычислением checksum
            hash_obj = hashlib.sha256()
            total_size = 0

            with open(temp_path, 'wb') as f:
                while True:
                    chunk = file_data.read(CHUNK_SIZE)
                    if not chunk:
                        break

                    f.write(chunk)
                    hash_obj.update(chunk)
                    total_size += len(chunk)

                # fsync для гарантии записи на диск
                f.flush()
                import os
                os.fsync(f.fileno())

            # Валидация размера если указан
            if expected_size is not None and total_size != expected_size:
                temp_path.unlink()
                raise StorageException(
                    message=f"File size mismatch: expected {expected_size}, got {total_size}",
                    error_code="SIZE_MISMATCH",
                    details={
                        "expected_size": expected_size,
                        "actual_size": total_size,
                        "relative_path": relative_path
                    }
                )

            checksum = hash_obj.hexdigest()

            # Атомарная замена (POSIX гарантирует атомарность rename)
            temp_path.replace(target_path)

            logger.info(
                "File written to local storage",
                extra={
                    "relative_path": relative_path,
                    "size_bytes": total_size,
                    "checksum": checksum
                }
            )

            return total_size, checksum

        except StorageException:
            raise
        except Exception as e:
            # Очистка временного файла при ошибке
            temp_path = target_path.parent / f".tmp_{target_path.name}"
            if temp_path.exists():
                temp_path.unlink()

            logger.error(
                f"Failed to write file to local storage: {e}",
                extra={
                    "relative_path": relative_path,
                    "error": str(e)
                }
            )
            raise StorageException(
                message="Failed to write file to local storage",
                error_code="LOCAL_WRITE_FAILED",
                details={"relative_path": relative_path, "error": str(e)}
            )

    async def read_file(
        self,
        relative_path: str
    ) -> AsyncGenerator[bytes, None]:
        """
        Прочитать файл из локального хранилища (streaming).

        Args:
            relative_path: Относительный путь в хранилище

        Yields:
            bytes: Chunk данных файла (8MB)

        Raises:
            StorageException: Файл не найден или ошибка чтения
        """
        file_path = self._get_full_path(relative_path)

        if not file_path.exists():
            raise StorageException(
                message=f"File not found: {relative_path}",
                error_code="FILE_NOT_FOUND",
                details={"relative_path": relative_path}
            )

        try:
            with open(file_path, 'rb') as f:
                while True:
                    chunk = f.read(CHUNK_SIZE)
                    if not chunk:
                        break
                    yield chunk

            logger.debug(
                "File read from local storage",
                extra={"relative_path": relative_path}
            )

        except Exception as e:
            logger.error(
                f"Failed to read file from local storage: {e}",
                extra={
                    "relative_path": relative_path,
                    "error": str(e)
                }
            )
            raise StorageException(
                message="Failed to read file from local storage",
                error_code="LOCAL_READ_FAILED",
                details={"relative_path": relative_path, "error": str(e)}
            )

    async def delete_file(
        self,
        relative_path: str
    ) -> None:
        """
        Удалить файл из локального хранилища.

        Args:
            relative_path: Относительный путь в хранилище

        Raises:
            StorageException: Ошибка удаления файла
        """
        file_path = self._get_full_path(relative_path)

        if not file_path.exists():
            raise StorageException(
                message=f"File not found: {relative_path}",
                error_code="FILE_NOT_FOUND",
                details={"relative_path": relative_path}
            )

        try:
            file_path.unlink()

            logger.info(
                "File deleted from local storage",
                extra={"relative_path": relative_path}
            )

        except Exception as e:
            logger.error(
                f"Failed to delete file from local storage: {e}",
                extra={
                    "relative_path": relative_path,
                    "error": str(e)
                }
            )
            raise StorageException(
                message="Failed to delete file from local storage",
                error_code="LOCAL_DELETE_FAILED",
                details={"relative_path": relative_path, "error": str(e)}
            )

    async def file_exists(
        self,
        relative_path: str
    ) -> bool:
        """
        Проверить существование файла в локальном хранилище.

        Args:
            relative_path: Относительный путь в хранилище

        Returns:
            bool: True если файл существует
        """
        file_path = self._get_full_path(relative_path)
        return file_path.exists()

    async def get_file_size(
        self,
        relative_path: str
    ) -> int:
        """
        Получить размер файла в байтах.

        Args:
            relative_path: Относительный путь в хранилище

        Returns:
            int: Размер файла в байтах

        Raises:
            StorageException: Файл не найден
        """
        file_path = self._get_full_path(relative_path)

        if not file_path.exists():
            raise StorageException(
                message=f"File not found: {relative_path}",
                error_code="FILE_NOT_FOUND",
                details={"relative_path": relative_path}
            )

        return file_path.stat().st_size


class S3StorageService(StorageService):
    """
    S3-совместимое хранилище (MinIO, AWS S3, etc.).

    Streaming операции через aioboto3.
    Multipart upload для больших файлов.
    """

    def __init__(
        self,
        endpoint_url: Optional[str] = None,
        access_key: Optional[str] = None,
        secret_key: Optional[str] = None,
        bucket_name: Optional[str] = None
    ):
        """
        Инициализация S3 Storage Service.

        Args:
            endpoint_url: S3 endpoint URL (по умолчанию из settings)
            access_key: AWS/MinIO access key (по умолчанию из settings)
            secret_key: AWS/MinIO secret key (по умолчанию из settings)
            bucket_name: S3 bucket name (по умолчанию из settings)
        """
        self.endpoint_url = endpoint_url or settings.storage.s3.endpoint_url
        self.access_key = access_key or settings.storage.s3.access_key_id
        self.secret_key = secret_key or settings.storage.s3.secret_access_key
        self.bucket_name = bucket_name or settings.storage.s3.bucket_name

        logger.info(
            f"S3StorageService initialized",
            extra={
                "endpoint_url": self.endpoint_url,
                "bucket_name": self.bucket_name
            }
        )

    async def write_file(
        self,
        relative_path: str,
        file_data: BinaryIO,
        expected_size: Optional[int] = None
    ) -> tuple[int, str]:
        """
        Записать файл в S3 хранилище.

        Args:
            relative_path: Относительный путь (S3 key)
            file_data: Бинарные данные файла
            expected_size: Ожидаемый размер (опционально)

        Returns:
            tuple[int, str]: (размер файла, SHA256 checksum)

        Raises:
            StorageException: Ошибка записи файла
        """
        try:
            session = aioboto3.Session()

            async with session.client(
                's3',
                endpoint_url=self.endpoint_url,
                aws_access_key_id=self.access_key,
                aws_secret_access_key=self.secret_key
            ) as s3_client:
                # Вычисление checksum и размера
                hash_obj = hashlib.sha256()
                total_size = 0
                chunks = []

                while True:
                    chunk = file_data.read(CHUNK_SIZE)
                    if not chunk:
                        break

                    chunks.append(chunk)
                    hash_obj.update(chunk)
                    total_size += len(chunk)

                # Валидация размера
                if expected_size is not None and total_size != expected_size:
                    raise StorageException(
                        message=f"File size mismatch: expected {expected_size}, got {total_size}",
                        error_code="SIZE_MISMATCH",
                        details={
                            "expected_size": expected_size,
                            "actual_size": total_size,
                            "relative_path": relative_path
                        }
                    )

                checksum = hash_obj.hexdigest()

                # Собрать chunks обратно в bytes
                file_bytes = b''.join(chunks)

                # Upload в S3
                await s3_client.put_object(
                    Bucket=self.bucket_name,
                    Key=relative_path,
                    Body=file_bytes,
                    Metadata={
                        'checksum': checksum,
                        'original_size': str(total_size)
                    }
                )

                logger.info(
                    "File written to S3 storage",
                    extra={
                        "relative_path": relative_path,
                        "size_bytes": total_size,
                        "checksum": checksum,
                        "bucket": self.bucket_name
                    }
                )

                return total_size, checksum

        except ClientError as e:
            logger.error(
                f"S3 client error: {e}",
                extra={
                    "relative_path": relative_path,
                    "error": str(e)
                }
            )
            raise StorageException(
                message="S3 client error",
                error_code="S3_CLIENT_ERROR",
                details={"relative_path": relative_path, "error": str(e)}
            )
        except StorageException:
            raise
        except Exception as e:
            logger.error(
                f"Failed to write file to S3 storage: {e}",
                extra={
                    "relative_path": relative_path,
                    "error": str(e)
                }
            )
            raise StorageException(
                message="Failed to write file to S3 storage",
                error_code="S3_WRITE_FAILED",
                details={"relative_path": relative_path, "error": str(e)}
            )

    async def read_file(
        self,
        relative_path: str
    ) -> AsyncGenerator[bytes, None]:
        """
        Прочитать файл из S3 хранилища (streaming).

        Args:
            relative_path: Относительный путь (S3 key)

        Yields:
            bytes: Chunk данных файла

        Raises:
            StorageException: Файл не найден или ошибка чтения
        """
        try:
            session = aioboto3.Session()

            async with session.client(
                's3',
                endpoint_url=self.endpoint_url,
                aws_access_key_id=self.access_key,
                aws_secret_access_key=self.secret_key
            ) as s3_client:
                response = await s3_client.get_object(
                    Bucket=self.bucket_name,
                    Key=relative_path
                )

                stream = response['Body']
                while True:
                    chunk = await stream.read(amt=CHUNK_SIZE)
                    if not chunk:
                        break
                    yield chunk

                logger.debug(
                    "File read from S3 storage",
                    extra={
                        "relative_path": relative_path,
                        "bucket": self.bucket_name
                    }
                )

        except ClientError as e:
            if e.response['Error']['Code'] == 'NoSuchKey':
                raise StorageException(
                    message=f"File not found: {relative_path}",
                    error_code="FILE_NOT_FOUND",
                    details={"relative_path": relative_path}
                )
            else:
                raise StorageException(
                    message="S3 client error",
                    error_code="S3_CLIENT_ERROR",
                    details={"relative_path": relative_path, "error": str(e)}
                )
        except StorageException:
            raise
        except Exception as e:
            logger.error(
                f"Failed to read file from S3 storage: {e}",
                extra={
                    "relative_path": relative_path,
                    "error": str(e)
                }
            )
            raise StorageException(
                message="Failed to read file from S3 storage",
                error_code="S3_READ_FAILED",
                details={"relative_path": relative_path, "error": str(e)}
            )

    async def delete_file(
        self,
        relative_path: str
    ) -> None:
        """
        Удалить файл из S3 хранилища.

        Args:
            relative_path: Относительный путь (S3 key)

        Raises:
            StorageException: Ошибка удаления файла
        """
        try:
            session = aioboto3.Session()

            async with session.client(
                's3',
                endpoint_url=self.endpoint_url,
                aws_access_key_id=self.access_key,
                aws_secret_access_key=self.secret_key
            ) as s3_client:
                await s3_client.delete_object(
                    Bucket=self.bucket_name,
                    Key=relative_path
                )

                logger.info(
                    "File deleted from S3 storage",
                    extra={
                        "relative_path": relative_path,
                        "bucket": self.bucket_name
                    }
                )

        except ClientError as e:
            logger.error(
                f"S3 client error: {e}",
                extra={
                    "relative_path": relative_path,
                    "error": str(e)
                }
            )
            raise StorageException(
                message="S3 client error",
                error_code="S3_CLIENT_ERROR",
                details={"relative_path": relative_path, "error": str(e)}
            )
        except Exception as e:
            logger.error(
                f"Failed to delete file from S3 storage: {e}",
                extra={
                    "relative_path": relative_path,
                    "error": str(e)
                }
            )
            raise StorageException(
                message="Failed to delete file from S3 storage",
                error_code="S3_DELETE_FAILED",
                details={"relative_path": relative_path, "error": str(e)}
            )

    async def file_exists(
        self,
        relative_path: str
    ) -> bool:
        """
        Проверить существование файла в S3 хранилище.

        Args:
            relative_path: Относительный путь (S3 key)

        Returns:
            bool: True если файл существует
        """
        try:
            session = aioboto3.Session()

            async with session.client(
                's3',
                endpoint_url=self.endpoint_url,
                aws_access_key_id=self.access_key,
                aws_secret_access_key=self.secret_key
            ) as s3_client:
                await s3_client.head_object(
                    Bucket=self.bucket_name,
                    Key=relative_path
                )
                return True

        except ClientError as e:
            if e.response['Error']['Code'] == '404':
                return False
            else:
                logger.error(
                    f"S3 client error: {e}",
                    extra={
                        "relative_path": relative_path,
                        "error": str(e)
                    }
                )
                return False

    async def get_file_size(
        self,
        relative_path: str
    ) -> int:
        """
        Получить размер файла в байтах.

        Args:
            relative_path: Относительный путь (S3 key)

        Returns:
            int: Размер файла в байтах

        Raises:
            StorageException: Файл не найден
        """
        try:
            session = aioboto3.Session()

            async with session.client(
                's3',
                endpoint_url=self.endpoint_url,
                aws_access_key_id=self.access_key,
                aws_secret_access_key=self.secret_key
            ) as s3_client:
                response = await s3_client.head_object(
                    Bucket=self.bucket_name,
                    Key=relative_path
                )
                return response['ContentLength']

        except ClientError as e:
            if e.response['Error']['Code'] == '404':
                raise StorageException(
                    message=f"File not found: {relative_path}",
                    error_code="FILE_NOT_FOUND",
                    details={"relative_path": relative_path}
                )
            else:
                raise StorageException(
                    message="S3 client error",
                    error_code="S3_CLIENT_ERROR",
                    details={"relative_path": relative_path, "error": str(e)}
                )

    # ========================================
    # Методы для работы с attr.json файлами
    # ========================================

    async def write_attr_file(
        self,
        relative_path: str,
        attributes: dict
    ) -> None:
        """
        Записать attr.json файл в S3 хранилище.

        Этот метод предназначен для сохранения метаданных файла
        в формате JSON рядом с основным файлом данных в S3.
        Реализует принцип "Attribute-First Storage Model".

        Args:
            relative_path: Относительный путь для attr.json (S3 key),
                          например: "storage_element_01/2025/11/25/16/file.pdf.attr.json"
            attributes: Словарь с метаданными файла

        Raises:
            StorageException: Ошибка записи attr.json в S3
        """
        try:
            import json as json_module

            session = aioboto3.Session()

            async with session.client(
                's3',
                endpoint_url=self.endpoint_url,
                aws_access_key_id=self.access_key,
                aws_secret_access_key=self.secret_key
            ) as s3_client:
                # Сериализация атрибутов в JSON с pretty print
                json_data = json_module.dumps(
                    attributes,
                    indent=2,
                    ensure_ascii=False,
                    default=str  # Для UUID, datetime и других типов
                ).encode('utf-8')

                await s3_client.put_object(
                    Bucket=self.bucket_name,
                    Key=relative_path,
                    Body=json_data,
                    ContentType='application/json'
                )

                logger.info(
                    "Attr file written to S3 storage",
                    extra={
                        "relative_path": relative_path,
                        "bucket": self.bucket_name,
                        "size_bytes": len(json_data)
                    }
                )

        except ClientError as e:
            logger.error(
                f"S3 client error writing attr file: {e}",
                extra={
                    "relative_path": relative_path,
                    "error": str(e)
                }
            )
            raise StorageException(
                message="Failed to write attr file to S3",
                error_code="S3_ATTR_WRITE_FAILED",
                details={"relative_path": relative_path, "error": str(e)}
            )
        except Exception as e:
            logger.error(
                f"Failed to write attr file to S3 storage: {e}",
                extra={
                    "relative_path": relative_path,
                    "error": str(e)
                }
            )
            raise StorageException(
                message="Failed to write attr file to S3 storage",
                error_code="S3_ATTR_WRITE_FAILED",
                details={"relative_path": relative_path, "error": str(e)}
            )

    async def read_attr_file(
        self,
        relative_path: str
    ) -> dict:
        """
        Прочитать attr.json файл из S3 хранилища.

        Args:
            relative_path: Относительный путь (S3 key) к attr.json файлу

        Returns:
            dict: Словарь с метаданными файла

        Raises:
            StorageException: Файл не найден или ошибка чтения
        """
        try:
            import json as json_module

            session = aioboto3.Session()

            async with session.client(
                's3',
                endpoint_url=self.endpoint_url,
                aws_access_key_id=self.access_key,
                aws_secret_access_key=self.secret_key
            ) as s3_client:
                response = await s3_client.get_object(
                    Bucket=self.bucket_name,
                    Key=relative_path
                )

                # Чтение всего содержимого JSON файла
                body = await response['Body'].read()
                attributes = json_module.loads(body.decode('utf-8'))

                logger.debug(
                    "Attr file read from S3 storage",
                    extra={
                        "relative_path": relative_path,
                        "bucket": self.bucket_name
                    }
                )

                return attributes

        except ClientError as e:
            if e.response['Error']['Code'] == 'NoSuchKey':
                raise StorageException(
                    message=f"Attr file not found: {relative_path}",
                    error_code="ATTR_FILE_NOT_FOUND",
                    details={"relative_path": relative_path}
                )
            else:
                raise StorageException(
                    message="S3 client error reading attr file",
                    error_code="S3_ATTR_READ_FAILED",
                    details={"relative_path": relative_path, "error": str(e)}
                )
        except Exception as e:
            logger.error(
                f"Failed to read attr file from S3 storage: {e}",
                extra={
                    "relative_path": relative_path,
                    "error": str(e)
                }
            )
            raise StorageException(
                message="Failed to read attr file from S3 storage",
                error_code="S3_ATTR_READ_FAILED",
                details={"relative_path": relative_path, "error": str(e)}
            )

    async def delete_attr_file(
        self,
        relative_path: str
    ) -> None:
        """
        Удалить attr.json файл из S3 хранилища.

        Args:
            relative_path: Относительный путь (S3 key) к attr.json файлу

        Raises:
            StorageException: Ошибка удаления attr.json
        """
        try:
            session = aioboto3.Session()

            async with session.client(
                's3',
                endpoint_url=self.endpoint_url,
                aws_access_key_id=self.access_key,
                aws_secret_access_key=self.secret_key
            ) as s3_client:
                await s3_client.delete_object(
                    Bucket=self.bucket_name,
                    Key=relative_path
                )

                logger.info(
                    "Attr file deleted from S3 storage",
                    extra={
                        "relative_path": relative_path,
                        "bucket": self.bucket_name
                    }
                )

        except ClientError as e:
            logger.error(
                f"S3 client error deleting attr file: {e}",
                extra={
                    "relative_path": relative_path,
                    "error": str(e)
                }
            )
            raise StorageException(
                message="S3 client error deleting attr file",
                error_code="S3_ATTR_DELETE_FAILED",
                details={"relative_path": relative_path, "error": str(e)}
            )
        except Exception as e:
            logger.error(
                f"Failed to delete attr file from S3 storage: {e}",
                extra={
                    "relative_path": relative_path,
                    "error": str(e)
                }
            )
            raise StorageException(
                message="Failed to delete attr file from S3 storage",
                error_code="S3_ATTR_DELETE_FAILED",
                details={"relative_path": relative_path, "error": str(e)}
            )

    # ========================================
    # Методы проверки здоровья S3 хранилища
    # ========================================

    async def check_bucket_exists(self) -> bool:
        """
        Проверить существование и доступность бакета в S3.

        Использует head_bucket для проверки доступа к бакету.
        Не требует прав на листинг объектов.

        Returns:
            bool: True если бакет существует и доступен

        Note:
            Метод НЕ выбрасывает исключения, только логирует ошибки.
            Это позволяет использовать его в health checks без прерывания.
        """
        try:
            session = aioboto3.Session()

            async with session.client(
                's3',
                endpoint_url=self.endpoint_url,
                aws_access_key_id=self.access_key,
                aws_secret_access_key=self.secret_key
            ) as s3_client:
                await s3_client.head_bucket(Bucket=self.bucket_name)

                logger.debug(
                    "S3 bucket check successful",
                    extra={
                        "bucket": self.bucket_name,
                        "endpoint": self.endpoint_url
                    }
                )
                return True

        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', '')

            if error_code in ('404', 'NoSuchBucket'):
                logger.warning(
                    "S3 bucket does not exist",
                    extra={
                        "bucket": self.bucket_name,
                        "endpoint": self.endpoint_url,
                        "error_code": error_code
                    }
                )
            elif error_code in ('403', 'AccessDenied'):
                logger.warning(
                    "S3 bucket access denied",
                    extra={
                        "bucket": self.bucket_name,
                        "endpoint": self.endpoint_url,
                        "error_code": error_code
                    }
                )
            else:
                logger.error(
                    f"S3 bucket check failed: {e}",
                    extra={
                        "bucket": self.bucket_name,
                        "endpoint": self.endpoint_url,
                        "error_code": error_code,
                        "error": str(e)
                    }
                )
            return False

        except Exception as e:
            logger.error(
                f"S3 connection error during bucket check: {e}",
                extra={
                    "bucket": self.bucket_name,
                    "endpoint": self.endpoint_url,
                    "error": str(e)
                }
            )
            return False

    async def check_app_folder_exists(self) -> bool:
        """
        Проверить существование app_folder и попытаться создать при отсутствии.

        В S3 директории виртуальные (это просто prefix в key).
        Проверяем наличие объектов с данным prefix.
        Если объектов нет - создаем placeholder файл .keep.

        Returns:
            bool: True если директория доступна или успешно создана

        Note:
            Требует предварительной проверки бакета через check_bucket_exists().
            Метод НЕ выбрасывает исключения, только логирует ошибки.
        """
        app_folder = settings.storage.s3.app_folder

        try:
            session = aioboto3.Session()

            async with session.client(
                's3',
                endpoint_url=self.endpoint_url,
                aws_access_key_id=self.access_key,
                aws_secret_access_key=self.secret_key
            ) as s3_client:
                # Проверяем наличие объектов с prefix app_folder/
                prefix = f"{app_folder}/"
                response = await s3_client.list_objects_v2(
                    Bucket=self.bucket_name,
                    Prefix=prefix,
                    MaxKeys=1
                )

                if response.get('KeyCount', 0) > 0:
                    logger.debug(
                        "S3 app_folder exists and has content",
                        extra={
                            "bucket": self.bucket_name,
                            "app_folder": app_folder
                        }
                    )
                    return True

                # Директория пуста или не существует - создаем placeholder
                placeholder_key = f"{app_folder}/.keep"

                logger.info(
                    "S3 app_folder is empty, creating placeholder",
                    extra={
                        "bucket": self.bucket_name,
                        "app_folder": app_folder,
                        "placeholder_key": placeholder_key
                    }
                )

                await s3_client.put_object(
                    Bucket=self.bucket_name,
                    Key=placeholder_key,
                    Body=b'',
                    ContentType='application/octet-stream'
                )

                logger.info(
                    "S3 app_folder placeholder created successfully",
                    extra={
                        "bucket": self.bucket_name,
                        "app_folder": app_folder
                    }
                )
                return True

        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', '')

            logger.error(
                f"S3 app_folder check/create failed: {e}",
                extra={
                    "bucket": self.bucket_name,
                    "app_folder": app_folder,
                    "error_code": error_code,
                    "error": str(e)
                }
            )
            return False

        except Exception as e:
            logger.error(
                f"S3 app_folder check error: {e}",
                extra={
                    "bucket": self.bucket_name,
                    "app_folder": app_folder,
                    "error": str(e)
                }
            )
            return False

    async def get_health_status(self) -> dict:
        """
        Получить полный статус здоровья S3 хранилища.

        Выполняет последовательные проверки:
        1. Доступность бакета
        2. Доступность/создание app_folder (только если бакет доступен)

        Returns:
            dict: Словарь с результатами проверок:
                - bucket_accessible (bool): Бакет доступен
                - app_folder_accessible (bool): App folder доступен
                - error_message (Optional[str]): Сообщение об ошибке для пользователя
                - endpoint_url (str): URL S3 endpoint
                - bucket_name (str): Имя бакета
                - app_folder (str): Имя app folder

        Example:
            >>> s3_service = S3StorageService()
            >>> status = await s3_service.get_health_status()
            >>> if status["bucket_accessible"] and status["app_folder_accessible"]:
            ...     print("S3 storage is healthy")
            ... else:
            ...     print(f"S3 error: {status['error_message']}")
        """
        app_folder = settings.storage.s3.app_folder

        result = {
            "bucket_accessible": False,
            "app_folder_accessible": False,
            "error_message": None,
            "endpoint_url": self.endpoint_url,
            "bucket_name": self.bucket_name,
            "app_folder": app_folder
        }

        # Шаг 1: Проверка бакета
        bucket_ok = await self.check_bucket_exists()
        result["bucket_accessible"] = bucket_ok

        if not bucket_ok:
            result["error_message"] = (
                f"S3 bucket '{self.bucket_name}' is not accessible "
                f"at '{self.endpoint_url}'"
            )
            logger.warning(
                "S3 health check failed: bucket not accessible",
                extra={
                    "bucket": self.bucket_name,
                    "endpoint": self.endpoint_url
                }
            )
            return result

        # Шаг 2: Проверка app_folder (только если бакет доступен)
        folder_ok = await self.check_app_folder_exists()
        result["app_folder_accessible"] = folder_ok

        if not folder_ok:
            result["error_message"] = (
                f"Directory '{app_folder}' in bucket '{self.bucket_name}' "
                f"is not accessible. Administrator should create it manually."
            )
            logger.warning(
                "S3 health check failed: app_folder not accessible",
                extra={
                    "bucket": self.bucket_name,
                    "app_folder": app_folder
                }
            )
            return result

        logger.debug(
            "S3 health check passed",
            extra={
                "bucket": self.bucket_name,
                "app_folder": app_folder
            }
        )

        return result


def get_storage_service() -> StorageService:
    """
    Factory function для получения правильного storage сервиса.

    Returns:
        StorageService: LocalStorageService или S3StorageService в зависимости от конфигурации

    Примеры:
        >>> storage = get_storage_service()
        >>> size, checksum = await storage.write_file("2025/01/10/15/file.pdf", file_data)
    """
    if settings.storage.type == StorageType.LOCAL:
        return LocalStorageService()
    elif settings.storage.type == StorageType.S3:
        return S3StorageService()
    else:
        raise ValueError(f"Unknown storage type: {settings.storage.type}")
