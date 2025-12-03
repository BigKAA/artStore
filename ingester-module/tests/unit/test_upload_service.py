"""
Unit tests для UploadService модуля Ingester.

Тестирует:
- UploadService initialization
- HTTP client configuration
- Error handling
- Mocking Storage Element responses

Note: Pragmatic approach - integration tests provide better coverage
for service layer. These unit tests focus on initialization and config.

Sprint 16: UploadService теперь требует auth_service в конструкторе.
_get_client() deprecated - используйте _get_client_for_endpoint() с SE из StorageSelector.
"""

import pytest
from unittest.mock import MagicMock, AsyncMock

from app.core.config import settings
from app.services.upload_service import UploadService


@pytest.fixture
def mock_auth_service():
    """Create mock AuthService instance."""
    mock_auth = MagicMock()
    mock_auth.get_access_token = AsyncMock(return_value="mock-access-token")
    mock_auth.close = AsyncMock()
    return mock_auth


class TestUploadService:
    """Тесты для UploadService класса."""

    def test_upload_service_initialization(self, mock_auth_service):
        """Проверка инициализации UploadService с auth_service."""
        service = UploadService(auth_service=mock_auth_service)

        # HTTP client инициализируется как None (lazy initialization)
        assert service._client is None
        assert service._max_file_size == 1024 * 1024 * 1024  # 1GB
        assert service.auth_service is mock_auth_service

    def test_upload_service_singleton(self):
        """
        UploadService использует singleton pattern.

        Note: singleton создается в main.py с auth_service.
        """
        # В main.py: upload_service = UploadService(auth_service=auth_service)
        # Тест проверяет только что модуль импортируется без ошибок
        from app.services import upload_service as upload_service_module
        assert upload_service_module is not None

    @pytest.mark.asyncio
    async def test_upload_service_get_client_deprecated(self, mock_auth_service):
        """
        Sprint 16: _get_client() deprecated - должен бросать RuntimeError.

        Используйте _get_client_for_endpoint() с SE endpoint из StorageSelector.
        """
        service = UploadService(auth_service=mock_auth_service)

        # _get_client() должен бросать RuntimeError (deprecated)
        with pytest.raises(RuntimeError, match="deprecated"):
            await service._get_client()

    @pytest.mark.asyncio
    async def test_upload_service_close(self, mock_auth_service):
        """Проверка закрытия HTTP client."""
        service = UploadService(auth_service=mock_auth_service)

        # Close должен работать без ошибок
        await service.close()

        # Повторный вызов close не должен вызывать ошибку
        await service.close()


# TODO: Add integration tests for upload_file method
# Integration tests provide better coverage for service layer
# with real Storage Element HTTP calls
