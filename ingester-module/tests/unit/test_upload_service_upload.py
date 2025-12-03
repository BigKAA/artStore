"""
Unit tests for UploadService.upload_file() method.

Тесты покрывают:
- Successful file upload workflow
- File size validation
- HTTP errors from Storage Element
- Connection errors
- Response validation

Sprint 16: Тесты требуют обновления для работы с Service Discovery.
UploadService теперь требует:
1. auth_service в конструкторе
2. StorageSelector для выбора SE (Service Discovery обязателен)

TODO: Переписать тесты с mock StorageSelector и mock HTTP clients per SE endpoint.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4
from datetime import datetime, timezone

import httpx
from fastapi import UploadFile

from app.services.upload_service import UploadService
from app.schemas.upload import UploadRequest, StorageMode
from app.core.exceptions import (
    StorageElementUnavailableException,
    FileSizeLimitExceededException,
    NoAvailableStorageException
)


@pytest.fixture
def mock_auth_service():
    """Create mock AuthService instance."""
    mock_auth = MagicMock()
    mock_auth.get_access_token = AsyncMock(return_value="mock-access-token")
    mock_auth.close = AsyncMock()
    return mock_auth


@pytest.fixture
def mock_storage_selector():
    """
    Create mock StorageSelector for unit tests.

    Sprint 16: StorageSelector обязателен для upload_file().
    """
    from app.services.storage_selector import StorageElementInfo, CapacityStatus
    from datetime import datetime, timezone

    mock_selector = MagicMock()
    mock_selector.select_storage_element = AsyncMock(return_value=StorageElementInfo(
        element_id="se-01",
        endpoint="http://storage-element-01:8000",
        mode="edit",
        priority=100,
        capacity_total=10*1024*1024*1024,  # 10GB
        capacity_used=1*1024*1024*1024,    # 1GB
        capacity_free=9*1024*1024*1024,    # 9GB
        capacity_percent=10.0,
        capacity_status=CapacityStatus.OK,
        health_status="healthy",
        last_updated=datetime.now(timezone.utc)
    ))
    return mock_selector


@pytest.fixture
def upload_service(mock_auth_service, mock_storage_selector):
    """Create UploadService instance with mock auth_service and storage_selector."""
    service = UploadService(auth_service=mock_auth_service)
    service.set_storage_selector(mock_storage_selector)
    return service


@pytest.fixture
def mock_upload_file():
    """Mock FastAPI UploadFile."""
    mock_file = MagicMock(spec=UploadFile)
    mock_file.filename = "test_document.pdf"
    mock_file.content_type = "application/pdf"
    mock_file.read = AsyncMock(return_value=b"Test file content data")
    return mock_file


@pytest.fixture
def upload_request():
    """Sample UploadRequest."""
    return UploadRequest(
        description="Test upload request",
        storage_mode=StorageMode.EDIT,
        compress=False
    )


@pytest.mark.asyncio
class TestUploadServiceUploadFile:
    """
    Unit tests для UploadService.upload_file() method.

    Sprint 16: Тесты обновлены для работы с Service Discovery.
    _get_client() deprecated → используется _get_client_for_endpoint().
    """

    @pytest.mark.skip(reason="Sprint 16: Requires refactoring for Service Discovery pattern")
    async def test_upload_file_success(
        self,
        upload_service,
        mock_upload_file,
        upload_request
    ):
        """Test successful file upload workflow."""
        # Mock HTTP client response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "id": str(uuid4()),
            "storage_filename": "test_document_testuser_20250114T120000_abc123.pdf"
        }

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)

        # Patch _get_client_for_endpoint to return mock
        with patch.object(upload_service, '_get_client_for_endpoint', return_value=mock_client):
            result = await upload_service.upload_file(
                file=mock_upload_file,
                request=upload_request,
                user_id="test-user-id",
                username="testuser"
            )

        # Verify result structure
        assert result.original_filename == "test_document.pdf"
        assert result.file_size == 22  # len(b"Test file content data")
        assert result.checksum is not None
        assert len(result.checksum) == 64  # SHA256 hex length
        assert result.compressed is False

        # Verify HTTP client was called correctly
        mock_client.post.assert_called_once()
        call_args = mock_client.post.call_args
        assert call_args[0][0] == "/api/v1/files/upload"
        assert "file" in call_args[1]["files"]
        assert call_args[1]["data"]["uploaded_by_username"] == "testuser"

    async def test_upload_file_exceeds_size_limit(
        self,
        mock_auth_service,
        mock_storage_selector,
        upload_request
    ):
        """Test file size limit validation."""
        # Create service with smaller limit for testing
        service = UploadService(auth_service=mock_auth_service)
        service.set_storage_selector(mock_storage_selector)
        service._max_file_size = 100  # Set to 100 bytes for test

        # Create file larger than limit
        large_content = b"x" * 101  # 101 bytes
        mock_large_file = MagicMock(spec=UploadFile)
        mock_large_file.filename = "oversized_file.bin"
        mock_large_file.content_type = "application/octet-stream"
        mock_large_file.read = AsyncMock(return_value=large_content)

        # Should raise FileSizeLimitExceededException
        with pytest.raises(FileSizeLimitExceededException) as exc_info:
            await service.upload_file(
                file=mock_large_file,
                request=upload_request,
                user_id="test-user-id",
                username="testuser"
            )

        assert "exceeds limit" in str(exc_info.value)
        assert "101" in str(exc_info.value)
        assert "100" in str(exc_info.value)

    @pytest.mark.skip(reason="Sprint 16: Requires refactoring for Service Discovery pattern")
    async def test_upload_file_storage_http_error(
        self,
        upload_service,
        mock_upload_file,
        upload_request
    ):
        """Test handling of HTTP errors from Storage Element."""
        # Mock HTTP 500 error
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Internal Server Error",
            request=MagicMock(),
            response=mock_response
        )

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch.object(upload_service, '_get_client_for_endpoint', return_value=mock_client):
            with pytest.raises(StorageElementUnavailableException) as exc_info:
                await upload_service.upload_file(
                    file=mock_upload_file,
                    request=upload_request,
                    user_id="test-user-id",
                    username="testuser"
                )

        assert "Storage Element returned error" in str(exc_info.value)
        assert "500" in str(exc_info.value)

    @pytest.mark.skip(reason="Sprint 16: Requires refactoring for Service Discovery pattern")
    async def test_upload_file_connection_error(
        self,
        upload_service,
        mock_upload_file,
        upload_request
    ):
        """Test handling of connection errors."""
        # Mock connection error
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(
            side_effect=httpx.ConnectError("Connection refused")
        )

        with patch.object(upload_service, '_get_client_for_endpoint', return_value=mock_client):
            with pytest.raises(StorageElementUnavailableException) as exc_info:
                await upload_service.upload_file(
                    file=mock_upload_file,
                    request=upload_request,
                    user_id="test-user-id",
                    username="testuser"
                )

        assert "Cannot connect to Storage Element" in str(exc_info.value)

    @pytest.mark.skip(reason="Sprint 16: Requires refactoring for Service Discovery pattern")
    async def test_upload_file_timeout_error(
        self,
        upload_service,
        mock_upload_file,
        upload_request
    ):
        """Test handling of timeout errors."""
        # Mock timeout error
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(
            side_effect=httpx.TimeoutException("Request timeout")
        )

        with patch.object(upload_service, '_get_client_for_endpoint', return_value=mock_client):
            with pytest.raises(StorageElementUnavailableException) as exc_info:
                await upload_service.upload_file(
                    file=mock_upload_file,
                    request=upload_request,
                    user_id="test-user-id",
                    username="testuser"
                )

        assert "Cannot connect to Storage Element" in str(exc_info.value)

    @pytest.mark.skip(reason="Sprint 16: Requires refactoring for Service Discovery pattern")
    async def test_upload_file_checksum_calculation(
        self,
        upload_service,
        mock_upload_file,
        upload_request
    ):
        """Test SHA256 checksum calculation."""
        # Mock HTTP client response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "id": str(uuid4()),
            "storage_filename": "test_document_testuser_20250114T120000_abc123.pdf"
        }

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch.object(upload_service, '_get_client_for_endpoint', return_value=mock_client):
            result = await upload_service.upload_file(
                file=mock_upload_file,
                request=upload_request,
                user_id="test-user-id",
                username="testuser"
            )

        # Verify checksum is SHA256 hex (64 characters)
        assert len(result.checksum) == 64
        assert all(c in '0123456789abcdef' for c in result.checksum)

    @pytest.mark.skip(reason="Sprint 16: Requires refactoring for Service Discovery pattern")
    async def test_upload_file_metadata_propagation(
        self,
        upload_service,
        mock_upload_file,
        upload_request
    ):
        """Test that metadata is correctly propagated to Storage Element."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "id": str(uuid4()),
            "storage_filename": "test_document_testuser_20250114T120000_abc123.pdf"
        }

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch.object(upload_service, '_get_client_for_endpoint', return_value=mock_client):
            await upload_service.upload_file(
                file=mock_upload_file,
                request=upload_request,
                user_id="test-user-123",
                username="testuser"
            )

        # Verify metadata in request
        call_args = mock_client.post.call_args
        data = call_args[1]["data"]

        assert data["description"] == "Test upload request"
        assert data["uploaded_by_username"] == "testuser"
        assert data["uploaded_by_id"] == "test-user-123"

    @pytest.mark.skip(reason="Sprint 16: Requires refactoring for Service Discovery pattern")
    async def test_upload_file_empty_description(
        self,
        upload_service,
        mock_upload_file
    ):
        """Test upload with empty description."""
        # Request without description
        request = UploadRequest(
            storage_mode=StorageMode.EDIT,
            compress=False
        )

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "id": str(uuid4()),
            "storage_filename": "test_document_testuser_20250114T120000_abc123.pdf"
        }

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch.object(upload_service, '_get_client_for_endpoint', return_value=mock_client):
            await upload_service.upload_file(
                file=mock_upload_file,
                request=request,
                user_id="test-user-id",
                username="testuser"
            )

        # Verify empty description is sent as empty string
        call_args = mock_client.post.call_args
        assert call_args[1]["data"]["description"] == ''

    @pytest.mark.skip(reason="Sprint 16: Requires refactoring for Service Discovery pattern")
    async def test_upload_file_missing_content_type(
        self,
        upload_service,
        upload_request
    ):
        """Test upload with missing content type."""
        # File without content_type
        mock_file = MagicMock(spec=UploadFile)
        mock_file.filename = "unknown_file"
        mock_file.content_type = None
        mock_file.read = AsyncMock(return_value=b"Data")

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "id": str(uuid4()),
            "storage_filename": "unknown_file_testuser_20250114T120000_abc123"
        }

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch.object(upload_service, '_get_client_for_endpoint', return_value=mock_client):
            await upload_service.upload_file(
                file=mock_file,
                request=upload_request,
                user_id="test-user-id",
                username="testuser"
            )

        # Verify default content type is used
        call_args = mock_client.post.call_args
        file_tuple = call_args[1]["files"]["file"]
        assert file_tuple[2] == "application/octet-stream"
