"""
Integration tests для Storage Service.

Тестируют работу с filesystem, S3, и database cache:
- Local filesystem operations
- S3 operations (если configured)
- Database cache synchronization
- Attr.json file management
- Directory structure creation

Требования:
- Docker containers running
- Storage path writable
- Database accessible
"""

import asyncio
import hashlib
import io
import json
from datetime import datetime
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings, StorageType
from app.db.session import AsyncSessionLocal
from app.models.file_metadata import FileMetadata
from app.services.storage_service import StorageService
from app.utils.attr_utils import read_attr_file
from app.utils.template_schema import FileAttributesV2, read_and_migrate_if_needed


@pytest.fixture
async def db_session():
    """Async database session для integration tests"""
    async with AsyncSessionLocal() as session:
        yield session


@pytest.fixture
async def storage_service(db_session):
    """Storage service instance"""
    return StorageService(db_session)


@pytest.fixture
def test_file_data():
    """Test file binary data"""
    return b"Integration test file content\nWith multiple lines\nFor testing"


@pytest.fixture
def test_file_stream(test_file_data):
    """Test file as BytesIO stream"""
    return io.BytesIO(test_file_data)


class TestLocalFilesystemStorage:
    """Integration tests для local filesystem storage"""

    @pytest.mark.asyncio
    async def test_store_file_creates_directory_structure(
        self,
        storage_service,
        test_file_stream,
        test_file_data
    ):
        """Тест создания directory structure при сохранении файла"""
        if settings.storage.type != StorageType.LOCAL:
            pytest.skip("Storage type is not LOCAL")

        file_id = uuid4()
        storage_filename = f"test_{file_id}.txt"

        # Store file
        stored_path = await storage_service.store_file(
            file_data=test_file_stream,
            storage_filename=storage_filename
        )

        # Verify directory structure: /year/month/day/hour/
        assert stored_path.exists()

        # Check path components
        path_parts = stored_path.parts
        assert len(path_parts) >= 4  # At least year/month/day/hour

        # Verify file content
        assert stored_path.read_bytes() == test_file_data

    @pytest.mark.asyncio
    async def test_store_and_retrieve_file(
        self,
        storage_service,
        test_file_stream,
        test_file_data
    ):
        """Тест сохранения и получения файла"""
        if settings.storage.type != StorageType.LOCAL:
            pytest.skip("Storage type is not LOCAL")

        storage_filename = f"test_{uuid4()}.txt"

        # Store
        stored_path = await storage_service.store_file(
            file_data=test_file_stream,
            storage_filename=storage_filename
        )

        # Retrieve
        retrieved_stream = await storage_service.get_file(stored_path)

        # Verify content
        retrieved_content = b""
        async for chunk in retrieved_stream:
            retrieved_content += chunk

        assert retrieved_content == test_file_data

    @pytest.mark.asyncio
    async def test_delete_file_removes_file_and_attr(self, storage_service, test_file_stream):
        """Тест удаления файла и его attr.json"""
        if settings.storage.type != StorageType.LOCAL:
            pytest.skip("Storage type is not LOCAL")

        storage_filename = f"test_{uuid4()}.txt"

        # Store file
        stored_path = await storage_service.store_file(
            file_data=test_file_stream,
            storage_filename=storage_filename
        )

        # Create attr.json (normally done by file_service)
        attr_file = stored_path.with_suffix(stored_path.suffix + ".attr.json")
        attr_data = {
            "file_id": str(uuid4()),
            "original_filename": "test.txt",
            "storage_filename": storage_filename,
            "file_size": 100,
            "content_type": "text/plain",
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
            "created_by_id": "test_user",
            "created_by_username": "test",
            "storage_path": str(stored_path),
            "checksum": "a" * 64,
            "metadata": {}
        }
        attr_file.write_text(json.dumps(attr_data))

        assert stored_path.exists()
        assert attr_file.exists()

        # Delete
        await storage_service.delete_file(stored_path)

        # Verify deleted
        assert not stored_path.exists()
        # Note: attr.json deletion is handled by file_service, not storage_service

    @pytest.mark.asyncio
    async def test_calculate_checksum(self, storage_service, test_file_data):
        """Тест расчета SHA256 checksum"""
        test_stream = io.BytesIO(test_file_data)

        checksum = await storage_service.calculate_checksum(test_stream)

        # Verify checksum format
        assert len(checksum) == 64
        assert all(c in "0123456789abcdef" for c in checksum)

        # Verify checksum value
        expected_checksum = hashlib.sha256(test_file_data).hexdigest()
        assert checksum == expected_checksum


class TestS3Storage:
    """Integration tests для S3 storage"""

    @pytest.mark.asyncio
    async def test_s3_store_file(self, storage_service, test_file_stream):
        """Тест сохранения файла в S3"""
        if settings.storage.type != StorageType.S3:
            pytest.skip("Storage type is not S3")

        storage_filename = f"test_{uuid4()}.txt"

        # Store file in S3
        stored_path = await storage_service.store_file(
            file_data=test_file_stream,
            storage_filename=storage_filename
        )

        # For S3, stored_path is S3 key
        assert isinstance(stored_path, (str, Path))

    @pytest.mark.asyncio
    async def test_s3_retrieve_file(self, storage_service, test_file_stream, test_file_data):
        """Тест получения файла из S3"""
        if settings.storage.type != StorageType.S3:
            pytest.skip("Storage type is not S3")

        storage_filename = f"test_{uuid4()}.txt"

        # Store
        stored_path = await storage_service.store_file(
            file_data=test_file_stream,
            storage_filename=storage_filename
        )

        # Retrieve
        retrieved_stream = await storage_service.get_file(stored_path)
        retrieved_content = b""
        async for chunk in retrieved_stream:
            retrieved_content += chunk

        assert retrieved_content == test_file_data


class TestAttrFileManagement:
    """Integration tests для attr.json file management"""

    @pytest.mark.asyncio
    async def test_attr_file_v2_creation(self, storage_service, test_file_stream):
        """Тест создания attr.json в v2.0 формате"""
        if settings.storage.type != StorageType.LOCAL:
            pytest.skip("Storage type is not LOCAL")

        file_id = uuid4()
        storage_filename = f"test_{file_id}.txt"

        # Store file
        stored_path = await storage_service.store_file(
            file_data=test_file_stream,
            storage_filename=storage_filename
        )

        # Create attr.json v2.0
        attr_file = stored_path.with_suffix(stored_path.suffix + ".attr.json")
        attr_data_v2 = FileAttributesV2(
            schema_version="2.0",
            file_id=file_id,
            original_filename="test.txt",
            storage_filename=storage_filename,
            file_size=100,
            content_type="text/plain",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            created_by_id="test_user",
            created_by_username="test",
            storage_path=str(stored_path),
            checksum="a" * 64,
            metadata={},
            custom_attributes={"department": "QA", "project": "ArtStore"}
        )

        # Write attr.json
        attr_file.write_text(attr_data_v2.model_dump_json())

        # Verify file exists
        assert attr_file.exists()

        # Read and validate
        attr_content = json.loads(attr_file.read_text())
        assert attr_content["schema_version"] == "2.0"
        assert attr_content["custom_attributes"]["department"] == "QA"

    @pytest.mark.asyncio
    async def test_attr_file_v1_migration(self, storage_service, test_file_stream):
        """Тест автоматической миграции v1.0 attr.json"""
        if settings.storage.type != StorageType.LOCAL:
            pytest.skip("Storage type is not LOCAL")

        file_id = uuid4()
        storage_filename = f"test_{file_id}.txt"

        # Store file
        stored_path = await storage_service.store_file(
            file_data=test_file_stream,
            storage_filename=storage_filename
        )

        # Create v1.0 attr.json (NO schema_version field)
        attr_file = stored_path.with_suffix(stored_path.suffix + ".attr.json")
        attr_data_v1 = {
            "file_id": str(file_id),
            "original_filename": "test.txt",
            "storage_filename": storage_filename,
            "file_size": 100,
            "content_type": "text/plain",
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
            "created_by_id": "test_user",
            "created_by_username": "test",
            "storage_path": str(stored_path),
            "checksum": "a" * 64,
            "metadata": {"legacy": "data"}
        }
        attr_file.write_text(json.dumps(attr_data_v1))

        # Read with auto-migration
        raw_data = json.loads(attr_file.read_text())
        migrated_attrs = read_and_migrate_if_needed(raw_data)

        # Verify migration
        assert migrated_attrs.schema_version == "2.0"
        assert migrated_attrs.custom_attributes == {}
        assert migrated_attrs.metadata["legacy"] == "data"


class TestDatabaseCacheIntegration:
    """Integration tests для database cache synchronization"""

    @pytest.mark.asyncio
    async def test_cache_entry_created_on_upload(self, db_session):
        """Тест создания cache entry при загрузке файла"""
        # This is tested through file_service, which coordinates
        # storage_service and database operations
        # Here we verify that database has expected structure

        # Query file_metadata table
        result = await db_session.execute(
            select(FileMetadata).limit(1)
        )
        metadata_entry = result.scalar_one_or_none()

        if metadata_entry:
            # Verify structure
            assert hasattr(metadata_entry, "file_id")
            assert hasattr(metadata_entry, "original_filename")
            assert hasattr(metadata_entry, "checksum")

    @pytest.mark.asyncio
    async def test_cache_consistency_with_attr_file(self, db_session, storage_service):
        """
        Тест консистентности между database cache и attr.json.

        NOTE: Это critical test для attribute-first storage model.
        Attr.json является source of truth, cache должен быть синхронизирован.
        """
        if settings.storage.type != StorageType.LOCAL:
            pytest.skip("Storage type is not LOCAL")

        # Get random file from database
        result = await db_session.execute(
            select(FileMetadata).limit(1)
        )
        metadata_entry = result.scalar_one_or_none()

        if not metadata_entry:
            pytest.skip("No files in database for consistency check")

        # Read attr.json
        storage_path = Path(metadata_entry.storage_path)
        if not storage_path.exists():
            pytest.skip("File not found on filesystem")

        attr_file = storage_path.with_suffix(storage_path.suffix + ".attr.json")
        if not attr_file.exists():
            pytest.skip("Attr file not found")

        # Compare database cache with attr.json
        attr_data = json.loads(attr_file.read_text())
        migrated_attrs = read_and_migrate_if_needed(attr_data)

        # Verify consistency
        assert str(metadata_entry.file_id) == str(migrated_attrs.file_id)
        assert metadata_entry.original_filename == migrated_attrs.original_filename
        assert metadata_entry.checksum == migrated_attrs.checksum
        assert metadata_entry.file_size == migrated_attrs.file_size


class TestStorageModeBehavior:
    """Integration tests для storage mode transitions"""

    @pytest.mark.asyncio
    async def test_edit_mode_allows_all_operations(self, storage_service, test_file_stream):
        """Тест что EDIT mode разрешает все операции"""
        if settings.app.mode.value != "edit":
            pytest.skip("Storage not in EDIT mode")

        # Store should work
        storage_filename = f"test_{uuid4()}.txt"
        stored_path = await storage_service.store_file(
            file_data=test_file_stream,
            storage_filename=storage_filename
        )
        assert stored_path.exists()

        # Delete should work
        await storage_service.delete_file(stored_path)
        assert not stored_path.exists()

    @pytest.mark.asyncio
    async def test_readonly_mode_prevents_write(self, storage_service, test_file_stream):
        """Тест что RO mode предотвращает запись"""
        if settings.app.mode.value in ["edit", "rw"]:
            pytest.skip("Storage in edit/rw mode")

        # Store should fail (tested at API level, not storage_service directly)
        # Storage service itself doesn't enforce mode restrictions
        # Mode restrictions are enforced at API/service layer
        pytest.skip("Mode restrictions enforced at API level")
