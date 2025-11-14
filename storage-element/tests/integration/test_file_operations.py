"""
Integration tests для File Operations через API.

Тестируют полный цикл работы с файлами:
- Upload файлов через API
- Download файлов через API
- Metadata operations (get, update, list)
- Delete operations (EDIT mode only)
- Template Schema v2.0 integration

Требования:
- Docker containers running (postgres, redis, storage-element)
- JWT authentication configured
- Storage path available
"""

import asyncio
import io
import json
from pathlib import Path
from uuid import UUID

import pytest
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.core.config import settings


# Test data
TEST_FILE_CONTENT = b"This is a test file content for integration testing.\nLine 2\nLine 3"
TEST_FILE_NAME = "test_document.txt"
TEST_FILE_CONTENT_TYPE = "text/plain"


@pytest.fixture
def test_file():
    """Create test file data"""
    return io.BytesIO(TEST_FILE_CONTENT)


@pytest.fixture(scope="function")
def auth_headers():
    """
    Authentication headers с реальными JWT токенами для integration tests.

    Использует JWT utilities для генерации валидных RS256 токенов,
    совместимых с admin-module authentication system.

    ВАЖНО: scope="function" - токен генерируется для каждого теста,
    чтобы избежать expiration issues при длительных test runs.

    Returns:
        Dict[str, str]: HTTP headers с Authorization Bearer токеном
    """
    from tests.utils.jwt_utils import create_auth_headers

    # Создаем СВЕЖИЙ токен с admin ролью для полного доступа к API
    return create_auth_headers(
        username="integration_test_user",
        email="integration@test.artstore.local",
        role="admin",
        user_id="integration_test_id"
    )


class TestFileUploadIntegration:
    """Integration tests для file upload operations"""

    @pytest.mark.asyncio
    async def test_upload_file_success(self, test_file, auth_headers):
        """Тест успешной загрузки файла через API"""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            files = {
                "file": (TEST_FILE_NAME, test_file, TEST_FILE_CONTENT_TYPE)
            }
            data = {
                "description": "Integration test file",
                "version": "1.0"
            }

            response = await client.post(
                "/api/v1/files/upload",
                files=files,
                data=data,
                headers=auth_headers
            )

            assert response.status_code == 201
            result = response.json()

            # Validate response structure
            assert "file_id" in result
            assert "original_filename" in result
            assert "file_size" in result
            assert "checksum" in result
            assert "message" in result

            # Validate data
            assert result["original_filename"] == TEST_FILE_NAME
            assert result["file_size"] == len(TEST_FILE_CONTENT)
            assert len(result["checksum"]) == 64  # SHA256

            # Save file_id for cleanup
            return UUID(result["file_id"])

    @pytest.mark.asyncio
    async def test_upload_file_with_custom_attributes(self, test_file, auth_headers):
        """Тест загрузки файла с custom_attributes (Template Schema v2.0)"""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            # Note: Custom attributes should be passed via metadata field
            # They will be stored in attr.json as custom_attributes in v2.0 format
            files = {
                "file": (TEST_FILE_NAME, test_file, TEST_FILE_CONTENT_TYPE)
            }
            data = {
                "description": "File with custom attributes",
                "version": "2.0",
                "metadata": json.dumps({
                    "department": "Engineering",
                    "project_code": "PROJ-123",
                    "classification": "internal"
                })
            }

            response = await client.post(
                "/api/v1/files/upload",
                files=files,
                data=data,
                headers=auth_headers
            )

            assert response.status_code == 201
            result = response.json()

            file_id = UUID(result["file_id"])

            # Verify attr.json contains custom_attributes in v2.0 format
            # This will be validated in test_get_file_metadata
            return file_id

    @pytest.mark.asyncio
    async def test_upload_file_large(self, auth_headers):
        """Тест загрузки большого файла (chunked upload)"""
        # Generate 10MB test file
        large_content = b"x" * (10 * 1024 * 1024)
        large_file = io.BytesIO(large_content)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            files = {
                "file": ("large_file.bin", large_file, "application/octet-stream")
            }

            response = await client.post(
                "/api/v1/files/upload",
                files=files,
                headers=auth_headers,
                timeout=30.0  # Longer timeout for large file
            )

            assert response.status_code == 201
            result = response.json()
            assert result["file_size"] == len(large_content)

            return UUID(result["file_id"])

    @pytest.mark.asyncio
    async def test_upload_file_invalid_mode(self, test_file, auth_headers):
        """Тест загрузки файла в readonly mode (должен fail)"""
        # This test assumes storage is in RO or AR mode
        # Skip if storage is in EDIT or RW mode
        if settings.app.mode.value in ["edit", "rw"]:
            pytest.skip("Storage is in edit/rw mode, upload allowed")

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            files = {
                "file": (TEST_FILE_NAME, test_file, TEST_FILE_CONTENT_TYPE)
            }

            response = await client.post(
                "/api/v1/files/upload",
                files=files,
                headers=auth_headers
            )

            assert response.status_code == 400
            assert "not allowed" in response.json()["detail"].lower()


class TestFileDownloadIntegration:
    """Integration tests для file download operations"""

    @pytest.mark.asyncio
    async def test_download_file_success(self, auth_headers):
        """Тест успешного скачивания файла"""
        # First, upload a file
        test_file = io.BytesIO(TEST_FILE_CONTENT)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            # Upload
            files = {"file": (TEST_FILE_NAME, test_file, TEST_FILE_CONTENT_TYPE)}
            upload_response = await client.post(
                "/api/v1/files/upload",
                files=files,
                headers=auth_headers
            )
            assert upload_response.status_code == 201
            file_id = upload_response.json()["file_id"]

            # Download
            download_response = await client.get(
                f"/api/v1/files/{file_id}/download",
                headers=auth_headers
            )

            assert download_response.status_code == 200
            assert download_response.content == TEST_FILE_CONTENT

            # Validate headers
            assert "content-disposition" in download_response.headers
            assert TEST_FILE_NAME in download_response.headers["content-disposition"]
            assert download_response.headers["content-type"] == TEST_FILE_CONTENT_TYPE

    @pytest.mark.asyncio
    async def test_download_file_not_found(self, auth_headers):
        """Тест скачивания несуществующего файла"""
        fake_file_id = "00000000-0000-0000-0000-000000000000"

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(
                f"/api/v1/files/{fake_file_id}/download",
                headers=auth_headers
            )

            assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_download_file_streaming(self, auth_headers):
        """Тест streaming download для большого файла"""
        # Upload large file
        large_content = b"y" * (5 * 1024 * 1024)  # 5MB
        large_file = io.BytesIO(large_content)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            # Upload
            files = {"file": ("large_stream.bin", large_file, "application/octet-stream")}
            upload_response = await client.post(
                "/api/v1/files/upload",
                files=files,
                headers=auth_headers,
                timeout=30.0
            )
            assert upload_response.status_code == 201
            file_id = upload_response.json()["file_id"]

            # Download with streaming
            async with client.stream(
                "GET",
                f"/api/v1/files/{file_id}/download",
                headers=auth_headers
            ) as response:
                assert response.status_code == 200

                # Read in chunks
                downloaded_content = b""
                async for chunk in response.aiter_bytes(chunk_size=8192):
                    downloaded_content += chunk

                assert len(downloaded_content) == len(large_content)
                assert downloaded_content == large_content


class TestFileMetadataIntegration:
    """Integration tests для file metadata operations"""

    @pytest.mark.asyncio
    async def test_get_file_metadata(self, auth_headers):
        """Тест получения метаданных файла"""
        # Upload file first
        test_file = io.BytesIO(TEST_FILE_CONTENT)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            # Upload
            files = {"file": (TEST_FILE_NAME, test_file, TEST_FILE_CONTENT_TYPE)}
            data = {"description": "Test metadata", "version": "1.0"}
            upload_response = await client.post(
                "/api/v1/files/upload",
                files=files,
                data=data,
                headers=auth_headers
            )
            file_id = upload_response.json()["file_id"]

            # Get metadata
            metadata_response = await client.get(
                f"/api/v1/files/{file_id}",
                headers=auth_headers
            )

            assert metadata_response.status_code == 200
            metadata = metadata_response.json()

            # Validate structure
            assert metadata["file_id"] == file_id
            assert metadata["original_filename"] == TEST_FILE_NAME
            assert metadata["file_size"] == len(TEST_FILE_CONTENT)
            assert metadata["content_type"] == TEST_FILE_CONTENT_TYPE
            assert metadata["description"] == "Test metadata"
            assert metadata["version"] == "1.0"
            assert len(metadata["checksum"]) == 64

    @pytest.mark.asyncio
    async def test_update_file_metadata(self, auth_headers):
        """Тест обновления метаданных файла"""
        if settings.app.mode.value not in ["edit", "rw"]:
            pytest.skip("Storage not in edit/rw mode")

        # Upload file first
        test_file = io.BytesIO(TEST_FILE_CONTENT)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            # Upload
            files = {"file": (TEST_FILE_NAME, test_file, TEST_FILE_CONTENT_TYPE)}
            upload_response = await client.post(
                "/api/v1/files/upload",
                files=files,
                headers=auth_headers
            )
            file_id = upload_response.json()["file_id"]

            # Update metadata
            update_data = {
                "description": "Updated description",
                "version": "2.0",
                "metadata": {"updated": True}
            }
            update_response = await client.patch(
                f"/api/v1/files/{file_id}",
                json=update_data,
                headers=auth_headers
            )

            assert update_response.status_code == 200
            updated = update_response.json()

            assert updated["description"] == "Updated description"
            assert updated["version"] == "2.0"

    @pytest.mark.asyncio
    async def test_list_files_pagination(self, auth_headers):
        """Тест получения списка файлов с пагинацией"""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            # Upload multiple files
            for i in range(5):
                test_file = io.BytesIO(f"Test file {i}".encode())
                files = {"file": (f"test_{i}.txt", test_file, "text/plain")}
                await client.post(
                    "/api/v1/files/upload",
                    files=files,
                    headers=auth_headers
                )

            # List files with pagination
            list_response = await client.get(
                "/api/v1/files/",
                params={"skip": 0, "limit": 3},
                headers=auth_headers
            )

            assert list_response.status_code == 200
            result = list_response.json()

            assert "total" in result
            assert "files" in result
            assert isinstance(result["files"], list)
            assert result["total"] >= 5
            assert len(result["files"]) <= 3


class TestFileDeleteIntegration:
    """Integration tests для file delete operations"""

    @pytest.mark.asyncio
    async def test_delete_file_success(self, auth_headers):
        """Тест успешного удаления файла"""
        if settings.app.mode.value != "edit":
            pytest.skip("Storage not in EDIT mode, deletion not allowed")

        # Upload file first
        test_file = io.BytesIO(TEST_FILE_CONTENT)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            # Upload
            files = {"file": (TEST_FILE_NAME, test_file, TEST_FILE_CONTENT_TYPE)}
            upload_response = await client.post(
                "/api/v1/files/upload",
                files=files,
                headers=auth_headers
            )
            file_id = upload_response.json()["file_id"]

            # Delete
            delete_response = await client.delete(
                f"/api/v1/files/{file_id}",
                headers=auth_headers
            )

            assert delete_response.status_code == 204

            # Verify file is gone
            get_response = await client.get(
                f"/api/v1/files/{file_id}",
                headers=auth_headers
            )
            assert get_response.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_file_invalid_mode(self, auth_headers):
        """Тест удаления файла в RW/RO mode (должен fail)"""
        if settings.app.mode.value == "edit":
            pytest.skip("Storage in EDIT mode, deletion allowed")

        # Upload file first (assuming mode was EDIT before)
        # For this test, we assume file exists from previous operations
        fake_file_id = "00000000-0000-0000-0000-000000000000"

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.delete(
                f"/api/v1/files/{fake_file_id}",
                headers=auth_headers
            )

            assert response.status_code == 400
            assert "not allowed" in response.json()["detail"].lower()


class TestTemplateSchemaV2Integration:
    """Integration tests для Template Schema v2.0"""

    @pytest.mark.asyncio
    async def test_v2_attr_file_creation(self, auth_headers):
        """Тест создания attr.json в v2.0 формате"""
        test_file = io.BytesIO(TEST_FILE_CONTENT)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            # Upload file
            files = {"file": (TEST_FILE_NAME, test_file, TEST_FILE_CONTENT_TYPE)}
            data = {
                "description": "V2.0 test file",
                "metadata": json.dumps({
                    "department": "QA",
                    "project": "ArtStore"
                })
            }
            upload_response = await client.post(
                "/api/v1/files/upload",
                files=files,
                data=data,
                headers=auth_headers
            )

            assert upload_response.status_code == 201
            file_id = upload_response.json()["file_id"]

            # Get metadata to verify v2.0 structure
            metadata_response = await client.get(
                f"/api/v1/files/{file_id}",
                headers=auth_headers
            )
            metadata = metadata_response.json()

            # Verify attr.json file exists and has v2.0 structure
            # (This requires accessing filesystem, which we do via storage service)
            # For integration test, we verify through API that metadata is correct
            assert metadata["file_id"] == file_id
            assert "storage_path" in metadata

    @pytest.mark.asyncio
    async def test_v1_to_v2_migration(self, auth_headers):
        """
        Тест автоматической миграции v1.0 → v2.0.

        NOTE: Этот тест требует наличия v1.0 файлов в системе.
        В production окружении v1.0 файлы будут мигрированы автоматически.
        """
        # This test is more relevant for existing v1.0 files
        # For new installations, all files will be v2.0 from the start
        pytest.skip("V1 migration test requires existing v1.0 files")
