"""
File upload service для Storage Element.

Обрабатывает загрузку файлов с streaming, WAL integration, и atomic writes.
"""

from fastapi import UploadFile
from sqlalchemy.orm import Session
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any
import hashlib
import uuid as uuid_lib

from app.core.config import get_config
from app.core.logging import get_logger
from app.core.atomic_write import (
    write_attr_file_atomic,
    WALManager,
    WALEntry,
    OperationType,
    OperationStatus
)
from app.utils.file_naming import generate_storage_filename
from app.models import FileMetadata, WAL

logger = get_logger()
config = get_config()


class FileUploadService:
    """
    Service для загрузки файлов с транзакционной безопасностью.

    Features:
    - Streaming upload для больших файлов
    - SHA256 checksum calculation on-the-fly
    - WAL-based transaction tracking
    - Atomic file and attr.json writes
    - Database metadata caching
    """

    def __init__(self, db: Session):
        """
        Initialize upload service.

        Args:
            db: Database session for metadata caching
        """
        self.db = db
        self.config = config
        self.logger = logger

        # Initialize WAL manager
        if config.wal.enabled:
            wal_dir = Path(config.wal.wal_dir)
            self.wal_manager = WALManager(wal_dir=wal_dir)
        else:
            self.wal_manager = WALManager()  # In-memory mode

        # Storage base path
        self.storage_base = Path(config.storage.local_base_path)

    async def upload_file(
        self,
        file: UploadFile,
        uploaded_by: str,
        uploader_full_name: Optional[str] = None,
        description: Optional[str] = None,
        retention_days: int = 365,
        tags: Optional[List[str]] = None
    ) -> FileMetadata:
        """
        Upload file with streaming and transactional safety.

        Process:
        1. Validate file and parameters
        2. Generate unique file_id and storage_filename
        3. Create WAL transaction entry
        4. Stream file to disk with SHA256 calculation
        5. Write attr.json atomically
        6. Cache metadata in database
        7. Commit WAL transaction

        Args:
            file: FastAPI UploadFile object
            uploaded_by: Username (required)
            uploader_full_name: Full name from LDAP
            description: Optional file description
            retention_days: Retention period (default 365)
            tags: Optional list of tags

        Returns:
            FileMetadata: Created file metadata object

        Raises:
            ValueError: Invalid parameters or file
            OSError: Storage errors (insufficient space, permissions)
        """
        # Validation
        self._validate_upload_params(file, uploaded_by, retention_days)

        # Generate unique identifiers
        file_id = uuid_lib.uuid4()
        timestamp = datetime.now(timezone.utc)

        # Generate storage filename
        storage_filename = generate_storage_filename(
            original_name=file.filename,
            username=uploaded_by,
            timestamp=timestamp
        )

        # Calculate storage path (year/month/day/hour)
        storage_path = self._calculate_storage_path(timestamp)
        full_storage_dir = self.storage_base / storage_path
        full_storage_dir.mkdir(parents=True, exist_ok=True)

        # Full file paths
        file_path = full_storage_dir / storage_filename
        attr_path = full_storage_dir / f"{storage_filename}.attr.json"

        self.logger.info(
            "Starting file upload",
            file_id=str(file_id),
            storage_filename=storage_filename,
            storage_path=storage_path
        )

        # Create WAL transaction
        transaction_id = uuid_lib.uuid4()
        wal_entry = WALEntry(
            transaction_id=transaction_id,
            operation_type=OperationType.UPLOAD,
            file_id=file_id,
            payload={
                "file_id": str(file_id),
                "original_filename": file.filename,
                "storage_filename": storage_filename,
                "storage_path": storage_path,
                "uploaded_by": uploaded_by
            },
            compensation_data={
                "action": "delete",
                "file_path": str(file_path),
                "attr_path": str(attr_path)
            }
        )

        # Write WAL entry
        self.wal_manager.write_wal_entry(wal_entry)

        try:
            # Stream file to disk with SHA256 calculation
            file_size, sha256_hash = await self._stream_file_to_disk(
                file=file,
                target_path=file_path
            )

            self.logger.info(
                "File streamed to disk",
                file_id=str(file_id),
                file_size=file_size,
                sha256=sha256_hash
            )

            # Calculate retention expiration
            retention_expires_at = timestamp + timedelta(days=retention_days)

            # Prepare attr.json attributes
            attributes = {
                "file_id": str(file_id),
                "original_filename": file.filename,
                "storage_filename": storage_filename,
                "storage_path": storage_path,
                "file_size": file_size,
                "mime_type": file.content_type or "application/octet-stream",
                "sha256": sha256_hash,
                "uploaded_at": timestamp.isoformat(),
                "uploaded_by": uploaded_by,
                "uploader_full_name": uploader_full_name,
                "description": description,
                "version": 1,
                "tags": tags or [],
                "retention_days": retention_days,
                "retention_expires_at": retention_expires_at.isoformat(),
                "created_at": timestamp.isoformat(),
                "updated_at": timestamp.isoformat()
            }

            # Write attr.json atomically
            write_attr_file_atomic(
                target_path=attr_path,
                attributes=attributes,
                wal_manager=self.wal_manager,
                transaction_id=transaction_id
            )

            self.logger.info(
                "Attr.json written atomically",
                file_id=str(file_id),
                attr_path=str(attr_path)
            )

            # Create database metadata cache
            file_metadata = FileMetadata(
                file_id=file_id,
                original_filename=file.filename,
                storage_filename=storage_filename,
                storage_path=storage_path,
                file_size=file_size,
                mime_type=file.content_type or "application/octet-stream",
                sha256=sha256_hash,
                uploaded_at=timestamp,
                uploaded_by=uploaded_by,
                uploader_full_name=uploader_full_name,
                description=description,
                version=1,
                tags=tags,
                retention_days=retention_days,
                retention_expires_at=retention_expires_at,
                created_at=timestamp,
                updated_at=timestamp
            )

            self.db.add(file_metadata)
            self.db.commit()
            self.db.refresh(file_metadata)

            self.logger.info(
                "File metadata cached in database",
                file_id=str(file_id)
            )

            # Commit WAL transaction
            self.wal_manager.update_wal_status(
                transaction_id=transaction_id,
                status=OperationStatus.COMMITTED
            )

            self.logger.info(
                "File upload completed successfully",
                file_id=str(file_id),
                transaction_id=str(transaction_id)
            )

            return file_metadata

        except Exception as e:
            # Rollback on error
            self.logger.error(
                "File upload failed, rolling back",
                file_id=str(file_id),
                transaction_id=str(transaction_id),
                error=str(e)
            )

            # Mark WAL as failed
            self.wal_manager.update_wal_status(
                transaction_id=transaction_id,
                status=OperationStatus.FAILED
            )

            # Cleanup files if they exist
            if file_path.exists():
                file_path.unlink()
                self.logger.info("Deleted file after failure", path=str(file_path))

            if attr_path.exists():
                attr_path.unlink()
                self.logger.info("Deleted attr.json after failure", path=str(attr_path))

            # Rollback database transaction
            self.db.rollback()

            raise

    async def _stream_file_to_disk(
        self,
        file: UploadFile,
        target_path: Path,
        chunk_size: int = 64 * 1024  # 64KB chunks
    ) -> tuple[int, str]:
        """
        Stream file to disk with SHA256 calculation.

        Args:
            file: UploadFile to stream
            target_path: Destination file path
            chunk_size: Chunk size for streaming (default 64KB)

        Returns:
            tuple: (file_size, sha256_hash)

        Raises:
            OSError: File system errors
        """
        sha256 = hashlib.sha256()
        file_size = 0

        try:
            with open(target_path, "wb") as f:
                while True:
                    chunk = await file.read(chunk_size)
                    if not chunk:
                        break

                    sha256.update(chunk)
                    f.write(chunk)
                    file_size += len(chunk)

                # Ensure data is written to disk
                f.flush()
                import os
                os.fsync(f.fileno())

        except Exception as e:
            # Cleanup on error
            if target_path.exists():
                target_path.unlink()
            raise

        return file_size, sha256.hexdigest()

    def _validate_upload_params(
        self,
        file: UploadFile,
        uploaded_by: str,
        retention_days: int
    ):
        """
        Validate upload parameters.

        Args:
            file: UploadFile to validate
            uploaded_by: Username to validate
            retention_days: Retention period to validate

        Raises:
            ValueError: Invalid parameters
        """
        if not file.filename:
            raise ValueError("Filename is required")

        if not uploaded_by or not uploaded_by.strip():
            raise ValueError("uploaded_by is required")

        if retention_days <= 0:
            raise ValueError("retention_days must be positive")

        if retention_days > 3650:  # 10 years max
            raise ValueError("retention_days cannot exceed 3650 days (10 years)")

        # Validate username for file naming
        if not all(c.isascii() and (c.isalnum() or c in ('-', '_')) for c in uploaded_by):
            raise ValueError(
                "uploaded_by must contain only ASCII alphanumeric characters, "
                "dashes, or underscores"
            )

    def _calculate_storage_path(self, timestamp: datetime) -> str:
        """
        Calculate hierarchical storage path.

        Args:
            timestamp: Upload timestamp

        Returns:
            str: Path in format "YYYY/MM/DD/HH"
        """
        return timestamp.strftime("%Y/%m/%d/%H")
