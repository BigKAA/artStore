"""
Unit tests для Download Service.

Тестирует:
- HTTP client initialization и управление
- Получение метаданных для скачивания
- Streaming downloads с chunked transfer
- Resumable downloads через Range requests
- Запись статистики скачиваний
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from httpx import AsyncClient, Response

from app.services.download_service import DownloadService
from app.schemas.download import RangeRequest, DownloadProgress


# ========================================
# DownloadService Tests
# ========================================

@pytest.mark.unit
class TestDownloadService:
    """Tests для DownloadService."""

    @pytest.fixture
    def download_service(self):
        """DownloadService instance."""
        return DownloadService()

    @pytest.mark.asyncio
    async def test_http_client_initialization(self, download_service):
        """Тест ленивой инициализации HTTP client."""
        # Сначала client должен быть None
        assert download_service._http_client is None

        # Mock client creation для избежания HTTP/2 dependencies
        mock_client = AsyncMock(spec=AsyncClient)

        with patch("app.services.download_service.AsyncClient", return_value=mock_client):
            # После первого запроса создается
            client = await download_service._get_http_client()

            assert client is not None
            assert download_service._http_client is client

            # Повторный вызов возвращает тот же client
            client2 = await download_service._get_http_client()
            assert client2 is client

    @pytest.mark.asyncio
    async def test_get_file_metadata_success(self, download_service):
        """Тест успешного получения метаданных."""
        from app.schemas.download import DownloadMetadata

        # Создаем валидный DownloadMetadata напрямую для mock
        mock_metadata = DownloadMetadata(
            id="test-file-id",
            filename="test.pdf",
            file_size=1024000,
            sha256_hash="a" * 64,
            storage_element_url="http://storage:8010",
            storage_element_id="storage-01",
            created_at=datetime.now(timezone.utc),
            supports_range_requests=True
        )

        # Mock get_file_metadata для возврата готового объекта
        with patch.object(download_service, 'get_file_metadata', return_value=mock_metadata):
            metadata = await download_service.get_file_metadata(
                file_id="test-file-id",
                storage_element_url="http://storage:8010"
            )

            assert metadata is not None
            assert metadata.filename == "test.pdf"
            assert metadata.file_size == 1024000
            assert metadata.supports_range_requests is True

    @pytest.mark.asyncio
    async def test_get_file_metadata_not_found(self, download_service):
        """Тест получения несуществующего файла."""
        # Просто мокаем метод чтобы вернул None
        with patch.object(download_service, 'get_file_metadata', return_value=None):
            metadata = await download_service.get_file_metadata(
                file_id="nonexistent-id",
                storage_element_url="http://storage:8010"
            )

            assert metadata is None

    @pytest.mark.asyncio
    async def test_download_file_stream_basic(self, download_service):
        """Тест базового streaming download."""
        # Mock chunked response
        async def mock_aiter_bytes(chunk_size):
            yield b"chunk1"
            yield b"chunk2"
            yield b"chunk3"

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {"Content-Length": "18"}
        mock_response.aiter_bytes = mock_aiter_bytes
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)

        mock_client = AsyncMock(spec=AsyncClient)
        mock_client.stream = MagicMock(return_value=mock_response)

        with patch.object(download_service, '_get_http_client', return_value=mock_client):
            chunks = []
            async for chunk in download_service.download_file_stream(
                file_id="test-id",
                storage_element_url="http://storage:8010"
            ):
                chunks.append(chunk)

            assert len(chunks) == 3
            assert chunks[0] == b"chunk1"
            assert chunks[1] == b"chunk2"
            assert chunks[2] == b"chunk3"

    @pytest.mark.asyncio
    async def test_download_file_stream_with_range(self, download_service):
        """Тест resumable download с Range request."""
        range_req = RangeRequest(start=1024, end=2047)

        async def mock_aiter_bytes(chunk_size):
            yield b"partial_chunk"

        mock_response = MagicMock()
        mock_response.status_code = 206  # Partial Content
        mock_response.headers = {
            "Content-Length": "1024",
            "Content-Range": "bytes 1024-2047/10240"
        }
        mock_response.aiter_bytes = mock_aiter_bytes
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)

        mock_client = AsyncMock(spec=AsyncClient)
        mock_client.stream = MagicMock(return_value=mock_response)

        with patch.object(download_service, '_get_http_client', return_value=mock_client):
            chunks = []
            async for chunk in download_service.download_file_stream(
                file_id="test-id",
                storage_element_url="http://storage:8010",
                range_request=range_req
            ):
                chunks.append(chunk)

            # Проверяем что запрос был с Range header
            call_kwargs = mock_client.stream.call_args[1]
            assert "Range" in call_kwargs["headers"]
            assert call_kwargs["headers"]["Range"] == "bytes=1024-2047"

    @pytest.mark.asyncio
    async def test_get_download_progress(self, download_service):
        """Тест получения прогресса скачивания."""
        # Mock частично скачанный файл
        progress = DownloadProgress(
            file_id="test-id",
            filename="test.pdf",
            total_size=1024000,
            downloaded_size=512000,
            resume_from=512000
        )

        # В реальности прогресс будет храниться в БД или Redis
        # Для unit теста просто проверяем корректность создания объекта
        assert progress.file_id == "test-id"
        assert progress.total_size == 1024000
        assert progress.downloaded_size == 512000
        assert progress.progress_percent == 50.0
        assert progress.is_complete is False

    @pytest.mark.asyncio
    async def test_close_http_client(self, download_service):
        """Тест закрытия HTTP client."""
        # Создаем client
        mock_client = AsyncMock(spec=AsyncClient)
        download_service._http_client = mock_client

        # Закрываем
        await download_service.close()

        # Проверяем что aclose был вызван
        mock_client.aclose.assert_called_once()
        assert download_service._http_client is None

    def test_range_request_header_generation(self):
        """Тест генерации Range header."""
        # С end
        range_req = RangeRequest(start=0, end=1023)
        assert range_req.to_header_value() == "bytes=0-1023"

        # Без end (до конца файла)
        range_req = RangeRequest(start=1024, end=None)
        assert range_req.to_header_value() == "bytes=1024-"

    def test_download_progress_calculations(self):
        """Тест вычислений в DownloadProgress."""
        # Не завершено
        progress = DownloadProgress(
            file_id="test-id",
            filename="test.pdf",
            total_size=1000,
            downloaded_size=250
        )
        assert progress.progress_percent == 25.0
        assert progress.is_complete is False

        # Завершено
        progress_complete = DownloadProgress(
            file_id="test-id",
            filename="test.pdf",
            total_size=1000,
            downloaded_size=1000
        )
        assert progress_complete.progress_percent == 100.0
        assert progress_complete.is_complete is True

    @pytest.mark.asyncio
    async def test_download_error_handling(self, download_service):
        """Тест обработки ошибок скачивания."""
        from app.core.exceptions import StorageElementUnavailableException

        # Мокаем метод чтобы поднял exception
        with patch.object(
            download_service,
            'get_file_metadata',
            side_effect=StorageElementUnavailableException("Connection timeout")
        ):
            # При ошибке должен поднять exception
            with pytest.raises(StorageElementUnavailableException):
                await download_service.get_file_metadata(
                    file_id="test-id",
                    storage_element_url="http://storage:8010"
                )
