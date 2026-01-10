"""
Local Filesystem Storage Backend.

Реализует StorageBackend интерфейс для локальной файловой системы.
"""

import json
import logging
import re
from pathlib import Path
from typing import AsyncGenerator, Optional

from app.core.config import settings
from app.services.storage_backends.base import StorageBackend, AttrFileInfo

logger = logging.getLogger(__name__)


class LocalBackend(StorageBackend):
    """Local Filesystem Storage Backend."""

    def __init__(self):
        """Инициализация local backend."""
        self.base_path = Path(settings.storage.local.base_path)

        if not self.base_path.exists():
            logger.warning(f"Storage base path does not exist: {self.base_path}")

    async def list_attr_files(
        self,
        prefix: Optional[str] = None,
        limit: Optional[int] = None
    ) -> AsyncGenerator[AttrFileInfo, None]:
        """Получить список attr.json файлов из локальной ФС."""
        search_path = self.base_path
        if prefix:
            search_path = self.base_path / prefix

        if not search_path.exists():
            logger.warning(f"Search path does not exist: {search_path}")
            return

        logger.info("Listing attr.json files from local filesystem", extra={"search_path": str(search_path)})

        # Рекурсивный поиск *.attr.json
        attr_files = search_path.rglob("*.attr.json")
        count = 0

        for attr_file_path in attr_files:
            relative_path = str(attr_file_path.relative_to(self.base_path))
            file_id = self._extract_file_id_from_path(relative_path)
            file_size = attr_file_path.stat().st_size

            yield AttrFileInfo(
                relative_path=relative_path,
                file_id=file_id,
                file_size=file_size
            )

            count += 1
            if limit and count >= limit:
                logger.info(f"Reached limit of {limit} attr.json files")
                break

        logger.info(f"Listed {count} attr.json files from local filesystem")

    async def read_attr_file(self, relative_path: str) -> dict:
        """Прочитать attr.json файл из локальной ФС."""
        attr_file_path = self.base_path / relative_path

        if not attr_file_path.exists():
            raise FileNotFoundError(f"Attr file not found: {relative_path}")

        try:
            with attr_file_path.open('r', encoding='utf-8') as f:
                return json.load(f)
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in attr file: {attr_file_path}")
            raise
        except Exception as e:
            logger.error(f"Failed to read attr file: {e}")
            raise

    async def file_exists(self, relative_path: str) -> bool:
        """Проверить существование data файла в локальной ФС."""
        data_file_path = self.base_path / relative_path
        return data_file_path.exists() and data_file_path.is_file()

    async def get_storage_info(self) -> dict:
        """Получить информацию о local storage."""
        accessible = self.base_path.exists() and self.base_path.is_dir()

        total_size = 0
        file_count = 0

        if accessible:
            try:
                for file_path in self.base_path.rglob("*"):
                    if file_path.is_file() and not file_path.name.endswith('.attr.json'):
                        file_count += 1
                        total_size += file_path.stat().st_size
            except Exception as e:
                logger.error(f"Failed to calculate storage info: {e}")

        return {
            "type": "local",
            "base_path": str(self.base_path),
            "accessible": accessible,
            "total_size_bytes": total_size,
            "file_count": file_count
        }

    def _extract_file_id_from_path(self, relative_path: str) -> str:
        """Извлечь file_id (UUID) из пути к attr.json."""
        filename = Path(relative_path).stem
        uuid_pattern = r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}'
        match = re.search(uuid_pattern, filename, re.IGNORECASE)

        if match:
            return match.group(0)
        else:
            logger.warning(f"Could not extract UUID from: {relative_path}")
            return relative_path
