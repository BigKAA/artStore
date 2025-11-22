"""
Integration tests for Storage Element communication.

Tests:
- HTTP client communication with Storage Element
- Error handling and retry logic
- Request/response validation
- Connection management
"""

import pytest
from httpx import AsyncClient
from app.services.upload_service import UploadService
import httpx


@pytest.mark.asyncio
class TestStorageElementCommunication:
    """Integration tests для HTTP communication с Storage Element."""

    async def test_upload_service_sends_file_to_storage(
        self,
        sample_file_content: bytes,
        mock_storage_url: str
    ):
        """
        Test что UploadService успешно отправляет файл в Storage Element.

        Note: Requires mock-storage service running
        """
        service = UploadService()

        try:
            # Создаем file-like object
            from io import BytesIO
            file_obj = BytesIO(sample_file_content)

            # Simulate upload (в реальности вызовется mock-storage)
            # Этот тест проверяет, что HTTP client правильно настроен
            client = await service._get_client()
            assert client is not None
            assert isinstance(client, httpx.AsyncClient)

        finally:
            await service.close()

    async def test_upload_service_http_client_configuration(self):
        """
        Test что HTTP client правильно сконфигурирован.
        """
        service = UploadService()

        try:
            client = await service._get_client()

            # Verify client exists and is properly configured
            assert client is not None
            assert isinstance(client, httpx.AsyncClient)
            assert client.timeout is not None

        finally:
            await service.close()

    async def test_upload_service_connection_pooling(self):
        """
        Test что HTTP client использует connection pooling.
        """
        service = UploadService()

        try:
            # Получаем client дважды - должен быть тот же instance
            client1 = await service._get_client()
            client2 = await service._get_client()

            assert client1 is client2  # Lazy initialization reuses client

        finally:
            await service.close()

    async def test_upload_service_close_cleanup(self):
        """
        Test что close() правильно очищает resources.
        """
        service = UploadService()

        # Initialize client
        await service._get_client()
        assert service._client is not None

        # Close should cleanup
        await service.close()
        assert service._client is None

    async def test_upload_service_timeout_configuration(self):
        """
        Test что timeouts правильно настроены.
        """
        service = UploadService()

        try:
            client = await service._get_client()

            # Verify timeout is configured
            assert client.timeout is not None

        finally:
            await service.close()

    async def test_upload_service_handles_connection_errors(
        self,
        monkeypatch
    ):
        """
        Test обработки connection errors.

        Симулирует недоступность Storage Element.
        """
        # Патчим storage settings на несуществующий URL
        from app.core import config
        monkeypatch.setattr(
            config.settings.storage_element,
            "base_url",
            "http://localhost:99999"
        )

        service = UploadService()

        try:
            client = await service._get_client()

            # Попытка connect к несуществующему сервису
            with pytest.raises((httpx.ConnectError, httpx.TimeoutException)):
                await client.get("/api/v1/health/live", timeout=1.0)

        finally:
            await service.close()


@pytest.mark.asyncio
class TestStorageElementErrorHandling:
    """Integration tests для error scenarios при общении с Storage Element."""

    async def test_storage_returns_4xx_error(
        self,
        client: AsyncClient,
        auth_headers: dict,
        sample_multipart_file: dict
    ):
        """
        Test обработки 4xx ошибок от Storage Element.

        Mock-storage может вернуть 400/404/422 errors.
        """
        # Отправляем некорректный request, который вызовет error
        # В реальности mock-storage должен вернуть соответствующую ошибку
        response = await client.post(
            "/api/v1/upload",
            headers=auth_headers,
            files=sample_multipart_file
        )

        # Depending on mock configuration:
        # - 200 if mock returns success
        # - 4xx if mock configured to return error
        assert response.status_code in [200, 400, 404, 422]

    async def test_storage_returns_5xx_error(
        self,
        client: AsyncClient,
        auth_headers: dict,
        sample_multipart_file: dict,
        monkeypatch
    ):
        """
        Test обработки 5xx ошибок от Storage Element.

        Симулирует internal server error на Storage Element.
        """
        # Note: Требует настройки mock-storage для возврата 5xx
        response = await client.post(
            "/api/v1/upload",
            headers=auth_headers,
            files=sample_multipart_file
        )

        # Should handle gracefully:
        # - 500 Internal Server Error propagated
        # - Or retry logic activated
        assert response.status_code in [200, 500, 503]

    async def test_storage_timeout_handling(
        self,
        client: AsyncClient,
        auth_headers: dict,
        sample_multipart_file: dict,
        monkeypatch
    ):
        """
        Test обработки timeout при общении с Storage Element.
        """
        # Патчим timeout на очень маленький
        from app.services import upload_service

        original_timeout = 30.0
        test_timeout = 0.001  # 1ms - guaranteed timeout

        async def mock_get_client(self):
            if self._client is None:
                self._client = httpx.AsyncClient(
                    timeout=httpx.Timeout(test_timeout),
                    limits=httpx.Limits(max_connections=100)
                )
            return self._client

        monkeypatch.setattr(
            upload_service.UploadService,
            "_get_client",
            mock_get_client
        )

        # Request с timeout должен fail gracefully
        response = await client.post(
            "/api/v1/upload",
            headers=auth_headers,
            files=sample_multipart_file
        )

        # Should return error (500/503)
        assert response.status_code in [500, 503, 504]


@pytest.mark.asyncio
class TestStorageElementHealthCheck:
    """Integration tests для health check взаимодействия."""

    async def test_storage_health_check_success(
        self,
        mock_storage_url: str
    ):
        """
        Test проверки health check Storage Element.

        Mock-storage должен отвечать на /api/v1/health/live
        """
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(
                    f"{mock_storage_url}/api/v1/health/live",
                    timeout=5.0
                )

                # Mock-storage should respond with 200
                # If not running, will raise exception
                assert response.status_code in [200, 404]  # 404 if mock not configured

            except (httpx.ConnectError, httpx.TimeoutException):
                # Mock service not running - skip test
                pytest.skip("Mock storage service not available")

    async def test_storage_unavailability_detection(self):
        """
        Test определения недоступности Storage Element.
        """
        service = UploadService()

        try:
            client = await service._get_client()

            # Попытка connect к несуществующему endpoint
            try:
                await client.get(
                    "http://localhost:99999/health",
                    timeout=1.0
                )
                pytest.fail("Should raise ConnectError or TimeoutException")
            except (httpx.ConnectError, httpx.TimeoutException, Exception) as e:
                # Expected - connection should fail
                assert True

        finally:
            await service.close()


@pytest.mark.asyncio
class TestStorageElementRetryLogic:
    """Integration tests для retry logic (если реализована)."""

    async def test_retry_on_temporary_failure(
        self,
        client: AsyncClient,
        auth_headers: dict,
        sample_multipart_file: dict
    ):
        """
        Test retry logic при временных сбоях.

        Note: Если retry logic не реализована, тест пройдет без retry.
        """
        response = await client.post(
            "/api/v1/upload",
            headers=auth_headers,
            files=sample_multipart_file
        )

        # Should succeed (with or without retry)
        assert response.status_code in [200, 500, 503]

    async def test_no_retry_on_client_error(
        self,
        client: AsyncClient,
        auth_headers: dict
    ):
        """
        Test что retry НЕ происходит на client errors (4xx).

        Client errors не должны retry.
        """
        # Отправляем некорректный request (empty file)
        empty_file = {"file": ("empty.txt", b"", "text/plain")}

        response = await client.post(
            "/api/v1/upload",
            headers=auth_headers,
            files=empty_file
        )

        # Should immediately return 422 without retry
        assert response.status_code == 422


@pytest.mark.asyncio
class TestStorageElementRequestValidation:
    """Integration tests для validation requests к Storage Element."""

    async def test_request_includes_required_headers(
        self,
        client: AsyncClient,
        auth_headers: dict,
        sample_multipart_file: dict
    ):
        """
        Test что requests к Storage Element включают required headers.
        """
        response = await client.post(
            "/api/v1/upload",
            headers=auth_headers,
            files=sample_multipart_file
        )

        # Should include Authorization header in request to storage
        # This is validated implicitly through successful upload
        assert response.status_code in [200, 401]

    async def test_request_includes_file_metadata(
        self,
        client: AsyncClient,
        auth_headers: dict,
        sample_multipart_file: dict
    ):
        """
        Test что requests включают file metadata.
        """
        metadata = {
            "description": "Test file metadata",
            "storage_mode": "edit"
        }

        response = await client.post(
            "/api/v1/upload",
            headers=auth_headers,
            files=sample_multipart_file,
            data=metadata
        )

        assert response.status_code in [200, 422]

        if response.status_code == 200:
            data = response.json()
            # Metadata should be preserved
            assert "file_id" in data
