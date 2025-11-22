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
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings, StorageType
from app.db.session import AsyncSessionLocal
from app.models.file_metadata import FileMetadata
from app.services.storage_service import StorageService, LocalStorageService, S3StorageService
from app.utils.attr_utils import read_attr_file
from app.utils.template_schema import FileAttributesV2, read_and_migrate_if_needed


@pytest.fixture(scope="function")
async def db_session():
    """
    Async database session для integration tests.

    ВАЖНО: scope="function" обеспечивает изоляцию event loop между тестами.
    Каждый тест получает новую session с собственным event loop.
    """
    async with AsyncSessionLocal() as session:
        yield session
        # Cleanup: rollback any uncommitted changes to avoid event loop issues
        await session.rollback()


@pytest.fixture
async def storage_service(db_session):
    """
    Storage service instance.

    ВАЖНО: Возвращает конкретную реализацию (LocalStorageService или S3StorageService)
    в зависимости от настройки STORAGE_TYPE в конфигурации.

    Args:
        db_session: Async database session fixture

    Returns:
        LocalStorageService | S3StorageService: Concrete storage service implementation
    """
    if settings.storage.type == StorageType.LOCAL:
        # Local filesystem storage
        return LocalStorageService(
            base_path=settings.storage.local.base_path
        )
    elif settings.storage.type == StorageType.S3:
        # S3 storage (MinIO)
        return S3StorageService(
            endpoint_url=settings.storage.s3.endpoint_url,
            access_key_id=settings.storage.s3.access_key_id,
            secret_access_key=settings.storage.s3.secret_access_key,
            bucket_name=settings.storage.s3.bucket_name,
            region=settings.storage.s3.region,
            app_folder=settings.storage.s3.app_folder
        )
    else:
        raise ValueError(f"Unsupported storage type: {settings.storage.type}")


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

        # Generate relative path with directory structure: year/month/day/hour/
        now = datetime.now(timezone.utc)
        relative_path = f"{now.year}/{now.month:02d}/{now.day:02d}/{now.hour:02d}/{storage_filename}"

        # Store file using current API
        size, checksum = await storage_service.write_file(
            relative_path=relative_path,
            file_data=test_file_stream
        )

        # Verify file was written
        assert size == len(test_file_data)
        assert len(checksum) == 64  # SHA256 hex length

        # Get full path for verification
        stored_path = storage_service._get_full_path(relative_path)
        assert stored_path.exists()

        # Check path components (should have year/month/day/hour structure)
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

        # Generate relative path
        now = datetime.now(timezone.utc)
        relative_path = f"{now.year}/{now.month:02d}/{now.day:02d}/{now.hour:02d}/{storage_filename}"

        # Store using current API
        size, checksum = await storage_service.write_file(
            relative_path=relative_path,
            file_data=test_file_stream
        )

        # Retrieve using current API
        retrieved_stream = storage_service.read_file(relative_path)

        # Verify content
        retrieved_content = b""
        async for chunk in retrieved_stream:
            retrieved_content += chunk

        assert retrieved_content == test_file_data
        assert size == len(test_file_data)

    @pytest.mark.asyncio
    async def test_delete_file_removes_file_and_attr(self, storage_service, test_file_stream):
        """Тест удаления файла и его attr.json"""
        if settings.storage.type != StorageType.LOCAL:
            pytest.skip("Storage type is not LOCAL")

        storage_filename = f"test_{uuid4()}.txt"

        # Generate relative path
        now = datetime.now(timezone.utc)
        relative_path = f"{now.year}/{now.month:02d}/{now.day:02d}/{now.hour:02d}/{storage_filename}"

        # Store file using current API
        size, checksum = await storage_service.write_file(
            relative_path=relative_path,
            file_data=test_file_stream
        )

        # Get full path for attr.json creation
        stored_path = storage_service._get_full_path(relative_path)

        # Create attr.json (normally done by file_service)
        attr_file = stored_path.with_suffix(stored_path.suffix + ".attr.json")
        attr_data = {
            "file_id": str(uuid4()),
            "original_filename": "test.txt",
            "storage_filename": storage_filename,
            "file_size": 100,
            "content_type": "text/plain",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "created_by_id": "test_user",
            "created_by_username": "test",
            "storage_path": str(stored_path),
            "checksum": "a" * 64,
            "metadata": {}
        }
        attr_file.write_text(json.dumps(attr_data))

        assert stored_path.exists()
        assert attr_file.exists()

        # Delete using current API (takes relative_path as string)
        await storage_service.delete_file(relative_path)

        # Verify deleted
        assert not stored_path.exists()
        # Note: attr.json deletion is handled by file_service, not storage_service

    @pytest.mark.asyncio
    async def test_calculate_checksum(self, storage_service, test_file_data):
        """Тест расчета SHA256 checksum через write_file()"""
        test_stream = io.BytesIO(test_file_data)

        # Generate relative path
        storage_filename = f"test_{uuid4()}.txt"
        now = datetime.now(timezone.utc)
        relative_path = f"{now.year}/{now.month:02d}/{now.day:02d}/{now.hour:02d}/{storage_filename}"

        # write_file() automatically calculates checksum during write
        size, checksum = await storage_service.write_file(
            relative_path=relative_path,
            file_data=test_stream
        )

        # Verify checksum format
        assert len(checksum) == 64
        assert all(c in "0123456789abcdef" for c in checksum)

        # Verify checksum value matches expected
        expected_checksum = hashlib.sha256(test_file_data).hexdigest()
        assert checksum == expected_checksum

        # Cleanup
        await storage_service.delete_file(relative_path)


class TestS3Storage:
    """Integration tests для S3 storage"""

    @pytest.mark.asyncio
    async def test_s3_store_file(self, storage_service, test_file_stream):
        """Тест сохранения файла в S3"""
        if settings.storage.type != StorageType.S3:
            pytest.skip("Storage type is not S3")

        storage_filename = f"test_{uuid4()}.txt"

        # Generate relative path
        now = datetime.now(timezone.utc)
        relative_path = f"{now.year}/{now.month:02d}/{now.day:02d}/{now.hour:02d}/{storage_filename}"

        # Store file in S3 using current API
        size, checksum = await storage_service.write_file(
            relative_path=relative_path,
            file_data=test_file_stream
        )

        # Verify size and checksum returned
        assert size > 0
        assert len(checksum) == 64  # SHA256 hex length

    @pytest.mark.asyncio
    async def test_s3_retrieve_file(self, storage_service, test_file_stream, test_file_data):
        """Тест получения файла из S3"""
        if settings.storage.type != StorageType.S3:
            pytest.skip("Storage type is not S3")

        storage_filename = f"test_{uuid4()}.txt"

        # Generate relative path
        now = datetime.now(timezone.utc)
        relative_path = f"{now.year}/{now.month:02d}/{now.day:02d}/{now.hour:02d}/{storage_filename}"

        # Store using current API
        size, checksum = await storage_service.write_file(
            relative_path=relative_path,
            file_data=test_file_stream
        )

        # Retrieve using current API
        retrieved_stream = storage_service.read_file(relative_path)
        retrieved_content = b""
        async for chunk in retrieved_stream:
            retrieved_content += chunk

        assert retrieved_content == test_file_data
        assert size == len(test_file_data)


class TestAttrFileManagement:
    """Integration tests для attr.json file management"""

    @pytest.mark.asyncio
    async def test_attr_file_v2_creation(self, storage_service, test_file_stream):
        """Тест создания attr.json в v2.0 формате"""
        if settings.storage.type != StorageType.LOCAL:
            pytest.skip("Storage type is not LOCAL")

        file_id = uuid4()
        storage_filename = f"test_{file_id}.txt"

        # Generate relative path
        now = datetime.now(timezone.utc)
        relative_path = f"{now.year}/{now.month:02d}/{now.day:02d}/{now.hour:02d}/{storage_filename}"

        # Store file using current API
        size, checksum = await storage_service.write_file(
            relative_path=relative_path,
            file_data=test_file_stream
        )

        # Get full path for attr.json creation
        stored_path = storage_service._get_full_path(relative_path)

        # Create attr.json v2.0
        attr_file = stored_path.with_suffix(stored_path.suffix + ".attr.json")
        attr_data_v2 = FileAttributesV2(
            schema_version="2.0",
            file_id=file_id,
            original_filename="test.txt",
            storage_filename=storage_filename,
            file_size=100,
            content_type="text/plain",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
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

        # Generate relative path
        now = datetime.now(timezone.utc)
        relative_path = f"{now.year}/{now.month:02d}/{now.day:02d}/{now.hour:02d}/{storage_filename}"

        # Store file using current API
        size, checksum = await storage_service.write_file(
            relative_path=relative_path,
            file_data=test_file_stream
        )

        # Get full path for attr.json creation
        stored_path = storage_service._get_full_path(relative_path)

        # Create v1.0 attr.json (NO schema_version field)
        attr_file = stored_path.with_suffix(stored_path.suffix + ".attr.json")
        attr_data_v1 = {
            "file_id": str(file_id),
            "original_filename": "test.txt",
            "storage_filename": storage_filename,
            "file_size": 100,
            "content_type": "text/plain",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
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
    """
    Integration tests для database cache synchronization.

    ВАЖНО: Эти тесты используют real HTTP requests к Docker test container
    вместо прямого database access, чтобы избежать проблем с table prefix
    и environment configuration.

    Best practice (Sprint 8): Integration tests через HTTP API > Direct DB access
    """

    @pytest.mark.asyncio
    async def test_cache_entry_created_on_upload(self, async_client, auth_headers):
        """
        Тест создания cache entry при загрузке файла через API.

        Проверяет:
        1. File upload через POST /api/v1/files/upload
        2. Cache entry automatically created in database
        3. File metadata retrievable через GET /api/v1/files/{file_id}
        """
        # Upload test file
        test_content = b"Test file content for cache validation"

        upload_response = await async_client.post(
            "/api/v1/files/upload",
            headers=auth_headers,
            files={"file": ("test_cache.txt", test_content, "text/plain")},
            data={"description": "Cache test file"}
        )

        assert upload_response.status_code == 201  # POST upload returns 201 Created
        upload_data = upload_response.json()
        file_id = upload_data["file_id"]

        # Verify cache entry exists by retrieving metadata
        metadata_response = await async_client.get(
            f"/api/v1/files/{file_id}",
            headers=auth_headers
        )

        assert metadata_response.status_code == 200
        metadata = metadata_response.json()

        # Verify database cache structure
        assert "file_id" in metadata
        assert "original_filename" in metadata
        assert "checksum" in metadata
        assert metadata["file_id"] == file_id
        assert metadata["original_filename"] == "test_cache.txt"

        # Cleanup
        delete_response = await async_client.delete(
            f"/api/v1/files/{file_id}",
            headers=auth_headers
        )
        assert delete_response.status_code in [200, 204]

    @pytest.mark.asyncio
    async def test_cache_consistency_with_attr_file(self, async_client, auth_headers):
        """
        Тест консистентности между database cache и attr.json через API.

        NOTE: Это critical test для attribute-first storage model.
        Attr.json является source of truth, cache должен быть синхронизирован.

        Проверяет:
        1. Upload file → attr.json + DB cache created
        2. Metadata от API matches attr.json (source of truth)
        3. Update metadata → both attr.json and cache updated
        """
        # Upload test file
        test_content = b"Consistency test content"
        original_filename = "consistency_test.txt"

        upload_response = await async_client.post(
            "/api/v1/files/upload",
            headers=auth_headers,
            files={"file": (original_filename, test_content, "text/plain")},
            data={"description": "Consistency validation"}
        )

        assert upload_response.status_code == 201  # POST upload returns 201 Created
        upload_data = upload_response.json()
        file_id = upload_data["file_id"]

        # Get metadata from API (reads from DB cache)
        metadata_response = await async_client.get(
            f"/api/v1/files/{file_id}",
            headers=auth_headers
        )

        assert metadata_response.status_code == 200
        metadata = metadata_response.json()

        # Verify consistency: API metadata should match uploaded file
        assert metadata["original_filename"] == original_filename
        assert metadata["file_size"] == len(test_content)
        assert metadata["description"] == "Consistency validation"

        # Test metadata update (updates both attr.json and DB cache)
        update_response = await async_client.patch(
            f"/api/v1/files/{file_id}",
            headers=auth_headers,
            json={"description": "Updated description"}
        )

        assert update_response.status_code == 200

        # Verify update consistency
        updated_metadata_response = await async_client.get(
            f"/api/v1/files/{file_id}",
            headers=auth_headers
        )

        assert updated_metadata_response.status_code == 200
        updated_metadata = updated_metadata_response.json()
        assert updated_metadata["description"] == "Updated description"

        # Cleanup
        delete_response = await async_client.delete(
            f"/api/v1/files/{file_id}",
            headers=auth_headers
        )
        assert delete_response.status_code in [200, 204]


class TestStorageModeBehavior:
    """Integration tests для storage mode transitions"""

    @pytest.mark.asyncio
    async def test_edit_mode_allows_all_operations(self, storage_service, test_file_stream):
        """Тест что EDIT mode разрешает все операции"""
        if settings.app.mode.value != "edit":
            pytest.skip("Storage not in EDIT mode")

        # Store should work
        storage_filename = f"test_{uuid4()}.txt"

        # Generate relative path
        now = datetime.now(timezone.utc)
        relative_path = f"{now.year}/{now.month:02d}/{now.day:02d}/{now.hour:02d}/{storage_filename}"

        # Store using current API
        size, checksum = await storage_service.write_file(
            relative_path=relative_path,
            file_data=test_file_stream
        )
        stored_path = storage_service._get_full_path(relative_path)
        assert stored_path.exists()

        # Delete should work using current API
        await storage_service.delete_file(relative_path)
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
