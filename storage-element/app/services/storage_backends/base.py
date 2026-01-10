"""
Абстрактный интерфейс для Storage Backend.

Унифицирует работу с S3 и локальной файловой системой для операций cache rebuild.
"""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import AsyncGenerator, Optional, List
from dataclasses import dataclass


@dataclass
class AttrFileInfo:
    """Информация об attr.json файле."""

    relative_path: str       # Относительный путь (e.g., "2025/11/25/16/file.pdf.attr.json")
    file_id: str            # UUID из имени файла или содержимого
    file_size: Optional[int] = None  # Размер attr.json (опционально)


class StorageBackend(ABC):
    """
    Абстрактный интерфейс для storage backend.

    Реализации:
    - S3Backend: для MinIO/S3
    - LocalBackend: для локальной файловой системы
    """

    @abstractmethod
    async def list_attr_files(
        self,
        prefix: Optional[str] = None,
        limit: Optional[int] = None
    ) -> AsyncGenerator[AttrFileInfo, None]:
        """
        Получить список всех attr.json файлов в хранилище.

        Args:
            prefix: Опциональный префикс для фильтрации (e.g., "2025/11/")
            limit: Опциональное ограничение количества файлов

        Yields:
            AttrFileInfo: Информация об attr.json файлах
        """
        pass

    @abstractmethod
    async def read_attr_file(self, relative_path: str) -> dict:
        """
        Прочитать содержимое attr.json файла.

        Args:
            relative_path: Относительный путь к attr.json файлу

        Returns:
            dict: Распарсенное содержимое attr.json

        Raises:
            FileNotFoundError: Если файл не найден
            JSONDecodeError: Если JSON невалидный
        """
        pass

    @abstractmethod
    async def file_exists(self, relative_path: str) -> bool:
        """
        Проверить существование data файла (не attr.json).

        Args:
            relative_path: Относительный путь к data файлу

        Returns:
            bool: True если файл существует
        """
        pass

    @abstractmethod
    async def get_storage_info(self) -> dict:
        """
        Получить информацию о storage backend.

        Returns:
            dict: Метаинформация (тип, размер, доступность и т.д.)
        """
        pass
