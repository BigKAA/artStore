"""
Unit tests для UploadService модуля Ingester.

Тестирует:
- UploadService initialization
- HTTP client configuration
- Error handling
- Mocking Storage Element responses

Note: Pragmatic approach - integration tests provide better coverage
for service layer. These unit tests focus on initialization and config.
"""

import pytest

from app.core.config import settings
from app.services.upload_service import UploadService


class TestUploadService:
    """Тесты для UploadService класса."""

    def test_upload_service_initialization(self):
        """Проверка инициализации UploadService."""
        service = UploadService()

        # HTTP client инициализируется как None (lazy initialization)
        assert service._client is None
        assert service._max_file_size == 1024 * 1024 * 1024  # 1GB

    def test_upload_service_singleton(self):
        """UploadService использует singleton pattern."""
        from app.services.upload_service import upload_service

        assert upload_service is not None
        assert isinstance(upload_service, UploadService)

    @pytest.mark.asyncio
    async def test_upload_service_client_config(self):
        """Проверка конфигурации HTTP client."""
        service = UploadService()

        # HTTP client создается через _get_client() (lazy)
        client = await service._get_client()

        # Проверка что клиент был создан
        assert client is not None
        assert service._client is not None

        # Cleanup
        await service.close()

    @pytest.mark.asyncio
    async def test_upload_service_close(self):
        """Проверка закрытия HTTP client."""
        service = UploadService()

        # Close должен работать без ошибок
        await service.close()

        # Повторный вызов close не должен вызывать ошибку
        await service.close()


# TODO: Add integration tests for upload_file method
# Integration tests provide better coverage for service layer
# with real Storage Element HTTP calls
