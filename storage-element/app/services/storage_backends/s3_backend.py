"""
S3 Storage Backend для MinIO/S3.

Реализует StorageBackend интерфейс для S3-совместимого хранилища.
"""

import json
import logging
import re
from pathlib import Path
from typing import AsyncGenerator, Optional

import boto3
from botocore.exceptions import ClientError

from app.core.config import settings
from app.services.storage_backends.base import StorageBackend, AttrFileInfo

logger = logging.getLogger(__name__)


class S3Backend(StorageBackend):
    """S3/MinIO Storage Backend."""

    def __init__(self):
        """Инициализация S3 backend."""
        self.bucket_name = settings.storage.s3.bucket_name
        self.app_folder = settings.storage.s3.app_folder
        self.endpoint_url = settings.storage.s3.endpoint_url

        # S3 client
        self.s3_client = boto3.client(
            's3',
            endpoint_url=self.endpoint_url,
            aws_access_key_id=settings.storage.s3.access_key_id,
            aws_secret_access_key=settings.storage.s3.secret_access_key,
        )

    async def list_attr_files(
        self,
        prefix: Optional[str] = None,
        limit: Optional[int] = None
    ) -> AsyncGenerator[AttrFileInfo, None]:
        """Получить список attr.json файлов из S3."""
        full_prefix = f"{self.app_folder}/"
        if prefix:
            full_prefix += prefix

        logger.info("Listing attr.json files from S3", extra={"bucket": self.bucket_name, "prefix": full_prefix})

        try:
            paginator = self.s3_client.get_paginator('list_objects_v2')
            page_iterator = paginator.paginate(Bucket=self.bucket_name, Prefix=full_prefix)

            count = 0
            for page in page_iterator:
                if 'Contents' not in page:
                    continue

                for obj in page['Contents']:
                    key = obj['Key']
                    if not key.endswith('.attr.json'):
                        continue

                    relative_path = key.replace(f"{self.app_folder}/", "")
                    file_id = self._extract_file_id_from_path(relative_path)

                    yield AttrFileInfo(
                        relative_path=relative_path,
                        file_id=file_id,
                        file_size=obj.get('Size')
                    )

                    count += 1
                    if limit and count >= limit:
                        logger.info(f"Reached limit of {limit} attr.json files")
                        return

            logger.info(f"Listed {count} attr.json files from S3")

        except ClientError as e:
            logger.error(f"Failed to list S3 objects: {e}")
            raise

    async def read_attr_file(self, relative_path: str) -> dict:
        """Прочитать attr.json файл из S3."""
        key = f"{self.app_folder}/{relative_path}"

        try:
            response = self.s3_client.get_object(Bucket=self.bucket_name, Key=key)
            content = response['Body'].read().decode('utf-8')
            return json.loads(content)

        except self.s3_client.exceptions.NoSuchKey:
            logger.warning(f"Attr file not found in S3: {key}")
            raise FileNotFoundError(f"Attr file not found: {relative_path}")

        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in attr file: {key}")
            raise

        except ClientError as e:
            logger.error(f"Failed to read attr file from S3: {e}")
            raise

    async def file_exists(self, relative_path: str) -> bool:
        """Проверить существование data файла в S3."""
        key = f"{self.app_folder}/{relative_path}"

        try:
            self.s3_client.head_object(Bucket=self.bucket_name, Key=key)
            return True
        except ClientError as e:
            if e.response['Error']['Code'] == '404':
                return False
            logger.error(f"Failed to check file existence: {e}")
            raise

    async def get_storage_info(self) -> dict:
        """Получить информацию о S3 storage."""
        try:
            self.s3_client.head_bucket(Bucket=self.bucket_name)
            return {
                "type": "s3",
                "bucket_name": self.bucket_name,
                "endpoint_url": self.endpoint_url,
                "app_folder": self.app_folder,
                "accessible": True
            }
        except ClientError as e:
            return {
                "type": "s3",
                "bucket_name": self.bucket_name,
                "accessible": False,
                "error": str(e)
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
