"""
Integration tests для Download API endpoints.

Тестирует:
- GET /api/download/{file_id}/metadata - Метаданные для скачивания
- GET /api/download/{file_id} - Скачивание файла
- HTTP Range requests для resumable downloads
- Streaming response behavior
- Error handling
"""

import pytest
from datetime import datetime, timezone
from fastapi import status
from httpx import AsyncClient
from unittest.mock import AsyncMock, patch, MagicMock

from app.main import app
from app.schemas.download import DownloadMetadata


# ========================================
# Download API Integration Tests
# ========================================

@pytest.mark.integration
@pytest.mark.asyncio
class TestDownloadAPIIntegration:
    """Integration tests для Download API."""

    async def test_get_download_metadata_success(
        self,
        valid_jwt_token,
        sample_file_metadata,
        mock_cache_service
    ):
        """Тест успешного получения метаданных для скачивания."""
        # Mock cache service возвращает метаданные
        mock_cache_service.get_file_metadata = lambda file_id: sample_file_metadata

        # Mock download service
        mock_metadata = DownloadMetadata(
            id=sample_file_metadata["id"],
            filename=sample_file_metadata["filename"],
            file_size=sample_file_metadata["file_size"],
            sha256_hash=sample_file_metadata["sha256_hash"],
            storage_element_url=sample_file_metadata["storage_element_url"],
            storage_element_id=sample_file_metadata["storage_element_id"],
            created_at=sample_file_metadata["created_at"],
            supports_range_requests=True
        )

        with patch("app.api.download.download_service.get_file_metadata", return_value=mock_metadata):
            async with AsyncClient(app=app, base_url="http://test") as client:
                response = await client.get(
                    f"/api/download/{sample_file_metadata['id']}/metadata",
                    headers={"Authorization": f"Bearer {valid_jwt_token}"}
                )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["id"] == sample_file_metadata["id"]
        assert data["filename"] == sample_file_metadata["filename"]
        assert data["file_size"] == sample_file_metadata["file_size"]
        assert data["supports_range_requests"] is True

    async def test_get_download_metadata_not_found(
        self,
        valid_jwt_token,
        mock_cache_service
    ):
        """Тест ошибки 404 для несуществующего файла."""
        # Mock cache service возвращает None
        mock_cache_service.get_file_metadata = lambda file_id: None

        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.get(
                "/api/download/nonexistent-id/metadata",
                headers={"Authorization": f"Bearer {valid_jwt_token}"}
            )

        assert response.status_code == status.HTTP_404_NOT_FOUND

    async def test_get_download_metadata_unauthorized(
        self,
        sample_file_metadata
    ):
        """Тест ошибки авторизации."""
        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.get(
                f"/api/download/{sample_file_metadata['id']}/metadata"
                # No Authorization header
            )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    async def test_download_file_success(
        self,
        valid_jwt_token,
        sample_file_metadata,
        mock_cache_service
    ):
        """Тест успешного скачивания файла."""
        # Mock cache service
        mock_cache_service.get_file_metadata = lambda file_id: sample_file_metadata

        # Mock download service stream
        async def mock_stream(*args, **kwargs):
            yield b"file content chunk 1"
            yield b"file content chunk 2"

        with patch("app.api.download.download_service.download_file_stream", return_value=mock_stream()):
            async with AsyncClient(app=app, base_url="http://test") as client:
                response = await client.get(
                    f"/api/download/{sample_file_metadata['id']}",
                    headers={"Authorization": f"Bearer {valid_jwt_token}"}
                )

        assert response.status_code == status.HTTP_200_OK
        assert response.headers["content-disposition"].startswith("attachment")
        assert "Accept-Ranges" in response.headers
        assert response.headers["Accept-Ranges"] == "bytes"

    async def test_download_file_with_range_request(
        self,
        valid_jwt_token,
        sample_file_metadata,
        mock_cache_service
    ):
        """Тест resumable download с Range request."""
        mock_cache_service.get_file_metadata = lambda file_id: sample_file_metadata

        async def mock_stream(*args, **kwargs):
            yield b"partial content"

        with patch("app.api.download.download_service.download_file_stream", return_value=mock_stream()):
            async with AsyncClient(app=app, base_url="http://test") as client:
                response = await client.get(
                    f"/api/download/{sample_file_metadata['id']}",
                    headers={
                        "Authorization": f"Bearer {valid_jwt_token}",
                        "Range": "bytes=0-1023"
                    }
                )

        # Partial Content response
        assert response.status_code == status.HTTP_206_PARTIAL_CONTENT
        assert "Accept-Ranges" in response.headers

    async def test_download_file_invalid_range_header(
        self,
        valid_jwt_token,
        sample_file_metadata,
        mock_cache_service
    ):
        """Тест обработки некорректного Range header."""
        mock_cache_service.get_file_metadata = lambda file_id: sample_file_metadata

        async def mock_stream(*args, **kwargs):
            yield b"full content"

        with patch("app.api.download.download_service.download_file_stream", return_value=mock_stream()):
            async with AsyncClient(app=app, base_url="http://test") as client:
                response = await client.get(
                    f"/api/download/{sample_file_metadata['id']}",
                    headers={
                        "Authorization": f"Bearer {valid_jwt_token}",
                        "Range": "invalid-range"
                    }
                )

        # Должен проигнорировать некорректный Range и вернуть 200
        assert response.status_code == status.HTTP_200_OK

    async def test_download_file_not_found(
        self,
        valid_jwt_token,
        mock_cache_service
    ):
        """Тест ошибки 404 для несуществующего файла."""
        mock_cache_service.get_file_metadata = lambda file_id: None

        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.get(
                "/api/download/nonexistent-id",
                headers={"Authorization": f"Bearer {valid_jwt_token}"}
            )

        assert response.status_code == status.HTTP_404_NOT_FOUND

    async def test_download_file_unauthorized(
        self,
        sample_file_metadata
    ):
        """Тест ошибки авторизации при скачивании."""
        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.get(
                f"/api/download/{sample_file_metadata['id']}"
                # No Authorization header
            )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED


# ========================================
# Streaming Download Tests
# ========================================

@pytest.mark.integration
@pytest.mark.asyncio
class TestStreamingDownloadIntegration:
    """Integration tests для streaming downloads."""

    async def test_streaming_download_large_file(
        self,
        valid_jwt_token,
        sample_file_metadata,
        mock_cache_service
    ):
        """Тест streaming download большого файла."""
        # Создаем большой файл (10MB simulated)
        large_file_metadata = {
            **sample_file_metadata,
            "file_size": 10 * 1024 * 1024  # 10MB
        }
        mock_cache_service.get_file_metadata = lambda file_id: large_file_metadata

        # Mock streaming chunks
        async def mock_stream(*args, **kwargs):
            # Симулируем 10 chunks по 1MB
            for i in range(10):
                yield b"x" * (1024 * 1024)

        with patch("app.api.download.download_service.download_file_stream", return_value=mock_stream()):
            async with AsyncClient(app=app, base_url="http://test") as client:
                response = await client.get(
                    f"/api/download/{sample_file_metadata['id']}",
                    headers={"Authorization": f"Bearer {valid_jwt_token}"}
                )

        assert response.status_code == status.HTTP_200_OK

        # Проверяем что получили весь контент
        total_bytes = 0
        async for chunk in response.aiter_bytes():
            total_bytes += len(chunk)

        assert total_bytes == 10 * 1024 * 1024

    async def test_resumable_download_from_offset(
        self,
        valid_jwt_token,
        sample_file_metadata,
        mock_cache_service
    ):
        """Тест возобновления скачивания с определенного offset."""
        mock_cache_service.get_file_metadata = lambda file_id: sample_file_metadata

        # Mock partial stream starting from byte 1024
        async def mock_stream(*args, **kwargs):
            # Возвращаем данные начиная с offset
            yield b"resumed content from byte 1024"

        with patch("app.api.download.download_service.download_file_stream", return_value=mock_stream()):
            async with AsyncClient(app=app, base_url="http://test") as client:
                response = await client.get(
                    f"/api/download/{sample_file_metadata['id']}",
                    headers={
                        "Authorization": f"Bearer {valid_jwt_token}",
                        "Range": "bytes=1024-"  # Resume from byte 1024
                    }
                )

        assert response.status_code == status.HTTP_206_PARTIAL_CONTENT

        content = b""
        async for chunk in response.aiter_bytes():
            content += chunk

        assert b"resumed content" in content
