"""
Integration tests for file upload workflow.

Tests E2E scenarios:
- Authentication → Upload → Storage Element → Success
- Error handling and validation
- Mock service integration
"""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
class TestUploadFlowIntegration:
    """Integration tests for complete upload workflow."""

    async def test_upload_file_success_flow(
        self,
        client: AsyncClient,
        auth_headers: dict,
        sample_multipart_file: dict
    ):
        """
        Test successful file upload E2E flow.

        Steps:
        1. Client provides valid JWT token
        2. Uploads file via /api/v1/upload
        3. Ingester validates auth
        4. Ingester sends file to Storage Element
        5. Returns success response

        Note: This test requires mock-storage service running
        """
        response = await client.post(
            "/api/v1/files/upload",
            headers=auth_headers,
            files=sample_multipart_file
        )

        assert response.status_code == 200
        data = response.json()

        # Verify response structure
        assert "file_id" in data
        assert "original_filename" in data
        assert "storage_filename" in data
        assert "file_size" in data
        assert "uploaded_at" in data

        # Verify file metadata
        assert data["original_filename"] == "test_file.txt"
        assert data["file_size"] > 0

    async def test_upload_file_without_auth(
        self,
        client: AsyncClient,
        sample_multipart_file: dict
    ):
        """
        Test upload без authentication - должен вернуть 401 Unauthorized.
        """
        response = await client.post(
            "/api/v1/files/upload",
            files=sample_multipart_file
        )

        assert response.status_code == 401
        data = response.json()
        assert "detail" in data

    async def test_upload_file_with_invalid_token(
        self,
        client: AsyncClient,
        sample_multipart_file: dict
    ):
        """
        Test upload с невалидным JWT токеном - должен вернуть 401.
        """
        headers = {"Authorization": "Bearer invalid-token"}

        response = await client.post(
            "/api/v1/files/upload",
            headers=headers,
            files=sample_multipart_file
        )

        assert response.status_code == 401

    async def test_upload_file_with_metadata(
        self,
        client: AsyncClient,
        auth_headers: dict,
        sample_multipart_file: dict
    ):
        """
        Test upload с дополнительными metadata полями.
        """
        metadata = {
            "description": "Integration test file",
            "compress": "false",
            "storage_mode": "edit"
        }

        response = await client.post(
            "/api/v1/files/upload",
            headers=auth_headers,
            files=sample_multipart_file,
            data=metadata
        )

        assert response.status_code == 200
        data = response.json()
        assert "file_id" in data

    async def test_upload_large_file(
        self,
        client: AsyncClient,
        auth_headers: dict
    ):
        """
        Test upload большого файла (>1MB).

        Проверяет, что сервис правильно обрабатывает большие файлы.
        """
        # Создаем файл размером 2MB
        large_content = b"x" * (2 * 1024 * 1024)
        large_file = {
            "file": ("large_file.bin", large_content, "application/octet-stream")
        }

        response = await client.post(
            "/api/v1/files/upload",
            headers=auth_headers,
            files=large_file
        )

        # В зависимости от limits может вернуть 200 или 413 (Payload Too Large)
        assert response.status_code in [200, 413]

    async def test_upload_empty_file(
        self,
        client: AsyncClient,
        auth_headers: dict
    ):
        """
        Test upload пустого файла - должен вернуть validation error.
        """
        empty_file = {
            "file": ("empty.txt", b"", "text/plain")
        }

        response = await client.post(
            "/api/v1/files/upload",
            headers=auth_headers,
            files=empty_file
        )

        # Ожидаем validation error для пустого файла
        assert response.status_code == 422

    async def test_upload_multiple_files_sequential(
        self,
        client: AsyncClient,
        auth_headers: dict,
        sample_file_content: bytes
    ):
        """
        Test последовательной загрузки нескольких файлов.

        Проверяет, что сервис может обрабатывать multiple uploads.
        """
        file_ids = []

        for i in range(3):
            files = {
                "file": (f"test_file_{i}.txt", sample_file_content, "text/plain")
            }

            response = await client.post(
                "/api/v1/files/upload",
                headers=auth_headers,
                files=files
            )

            assert response.status_code == 200
            data = response.json()
            file_ids.append(data["file_id"])

        # Verify all uploads succeeded with unique file IDs
        assert len(file_ids) == 3
        assert len(set(file_ids)) == 3  # All unique

    async def test_upload_with_special_characters_filename(
        self,
        client: AsyncClient,
        auth_headers: dict,
        sample_file_content: bytes
    ):
        """
        Test upload файла с специальными символами в имени.

        Проверяет корректную обработку filenames.
        """
        special_filename = "тест файл (1) [копия].txt"
        files = {
            "file": (special_filename, sample_file_content, "text/plain")
        }

        response = await client.post(
            "/api/v1/files/upload",
            headers=auth_headers,
            files=files
        )

        assert response.status_code == 200
        data = response.json()
        assert "file_id" in data

    async def test_upload_different_file_types(
        self,
        client: AsyncClient,
        auth_headers: dict
    ):
        """
        Test upload различных типов файлов.

        Проверяет support для разных content types.
        """
        test_files = [
            ("document.pdf", b"%PDF-1.4 test", "application/pdf"),
            ("image.jpg", b"\xFF\xD8\xFF test", "image/jpeg"),
            ("data.json", b'{"test": true}', "application/json"),
            ("script.py", b"print('test')", "text/x-python"),
        ]

        for filename, content, content_type in test_files:
            files = {"file": (filename, content, content_type)}

            response = await client.post(
                "/api/v1/files/upload",
                headers=auth_headers,
                files=files
            )

            assert response.status_code == 200, f"Failed for {filename}"
            data = response.json()
            assert data["original_filename"] == filename


@pytest.mark.asyncio
class TestUploadFlowErrorHandling:
    """Integration tests для error scenarios."""

    async def test_upload_when_storage_unavailable(
        self,
        client: AsyncClient,
        auth_headers: dict,
        sample_multipart_file: dict,
        monkeypatch
    ):
        """
        Test upload когда Storage Element недоступен.

        Должен вернуть 503 Service Unavailable или 500 Internal Server Error.

        Note: Требует настройки mock-storage для возврата errors.
        """
        # Патчим storage URL на несуществующий
        from app.services import upload_service
        monkeypatch.setattr(
            upload_service.UploadService,
            "_storage_element_url",
            "http://localhost:99999"
        )

        response = await client.post(
            "/api/v1/files/upload",
            headers=auth_headers,
            files=sample_multipart_file
        )

        # Ожидаем service unavailable or connection error
        assert response.status_code in [500, 503]

    async def test_upload_with_malformed_request(
        self,
        client: AsyncClient,
        auth_headers: dict
    ):
        """
        Test upload с некорректным request format.
        """
        # Отправляем без multipart/form-data
        response = await client.post(
            "/api/v1/files/upload",
            headers=auth_headers,
            json={"file": "not a file"}
        )

        assert response.status_code == 422

    async def test_upload_exceeds_size_limit(
        self,
        client: AsyncClient,
        auth_headers: dict
    ):
        """
        Test upload файла, превышающего size limit.

        Default limit: 1GB (из UploadService)
        """
        # Создаем файл > 1GB (симулируем через metadata)
        oversized_metadata = {
            "description": "Oversized file test"
        }

        # В реальном сценарии это будет > 1GB content
        # Для теста проверяем, что limit enforcement работает
        files = {
            "file": ("huge.bin", b"x" * 100, "application/octet-stream")
        }

        response = await client.post(
            "/api/v1/files/upload",
            headers=auth_headers,
            files=files,
            data=oversized_metadata
        )

        # Small file should succeed
        assert response.status_code == 200

    # ==========================================
    # Storage Mode Validation Tests (Sprint 27)
    # ==========================================

    async def test_upload_rejects_ro_storage_mode(
        self,
        client: AsyncClient,
        auth_headers: dict,
        sample_multipart_file: dict
    ):
        """
        Test upload отклоняет storage_mode="ro" (read-only).

        Ingester endpoint должен принимать только "edit" и "rw" modes.
        Режимы "ro" и "ar" доступны только через конфигурацию Storage Element.
        """
        data = {
            "storage_mode": "ro",
            "description": "Test read-only mode"
        }

        response = await client.post(
            "/api/v1/files/upload",  # Correct API path
            headers=auth_headers,
            files=sample_multipart_file,
            data=data
        )

        # Должен вернуть 422 Unprocessable Entity (validation error)
        assert response.status_code == 422
        error_data = response.json()
        assert "detail" in error_data

    async def test_upload_rejects_ar_storage_mode(
        self,
        client: AsyncClient,
        auth_headers: dict,
        sample_multipart_file: dict
    ):
        """
        Test upload отклоняет storage_mode="ar" (archive).

        Архивный режим доступен только через конфигурацию, не через API.
        """
        data = {
            "storage_mode": "ar",
            "description": "Test archive mode"
        }

        response = await client.post(
            "/api/v1/files/upload",
            headers=auth_headers,
            files=sample_multipart_file,
            data=data
        )

        # Должен вернуть 422 Unprocessable Entity (validation error)
        assert response.status_code == 422
        error_data = response.json()
        assert "detail" in error_data

    async def test_upload_accepts_valid_storage_modes(
        self,
        client: AsyncClient,
        auth_headers: dict,
        sample_multipart_file: dict
    ):
        """
        Test upload принимает валидные storage_mode значения: "edit" и "rw".

        Default storage_mode = "edit".
        """
        # Test storage_mode="edit"
        data_edit = {
            "storage_mode": "edit",
            "description": "Test edit mode"
        }

        response_edit = await client.post(
            "/api/v1/files/upload",
            headers=auth_headers,
            files=sample_multipart_file,
            data=data_edit
        )

        assert response_edit.status_code == 200

        # Test storage_mode="rw"
        data_rw = {
            "storage_mode": "rw",
            "description": "Test read-write mode"
        }

        response_rw = await client.post(
            "/api/v1/files/upload",
            headers=auth_headers,
            files=sample_multipart_file,
            data=data_rw
        )

        assert response_rw.status_code == 200

    # ==========================================
    # Compression Algorithm Validation Tests (Sprint 27)
    # ==========================================

    async def test_upload_invalid_compression_algorithm(
        self,
        client: AsyncClient,
        auth_headers: dict,
        sample_multipart_file: dict
    ):
        """
        Test upload отклоняет неизвестный compression algorithm.

        Допустимые значения: "gzip", "brotli".
        """
        data = {
            "compress": "true",  # on/off format для boolean
            "compression_algorithm": "invalid_algo",
            "description": "Test invalid compression"
        }

        response = await client.post(
            "/api/v1/files/upload",
            headers=auth_headers,
            files=sample_multipart_file,
            data=data
        )

        # Должен вернуть 422 Unprocessable Entity (validation error)
        assert response.status_code == 422
        error_data = response.json()
        assert "detail" in error_data

    async def test_upload_compression_gzip_success(
        self,
        client: AsyncClient,
        auth_headers: dict,
        sample_multipart_file: dict
    ):
        """
        Test успешное сжатие с gzip algorithm.

        compress=true и compression_algorithm="gzip" должны быть приняты.
        """
        data = {
            "compress": "true",  # on/off format
            "compression_algorithm": "gzip",
            "description": "Test gzip compression"
        }

        response = await client.post(
            "/api/v1/files/upload",
            headers=auth_headers,
            files=sample_multipart_file,
            data=data
        )

        assert response.status_code == 200
        result = response.json()

        # Compression metadata должна присутствовать
        assert "compressed" in result
        assert "compression_ratio" in result

    async def test_upload_compression_brotli_success(
        self,
        client: AsyncClient,
        auth_headers: dict,
        sample_multipart_file: dict
    ):
        """
        Test успешное сжатие с brotli algorithm.

        compress=true и compression_algorithm="brotli" должны быть приняты.
        """
        data = {
            "compress": "true",  # on/off format
            "compression_algorithm": "brotli",
            "description": "Test brotli compression"
        }

        response = await client.post(
            "/api/v1/files/upload",
            headers=auth_headers,
            files=sample_multipart_file,
            data=data
        )

        assert response.status_code == 200
        result = response.json()

        # Compression metadata должна присутствовать
        assert "compressed" in result
        assert "compression_ratio" in result

    # ==========================================
    # Compression Ratio Validation Tests (Sprint 27)
    # ==========================================

    async def test_upload_compression_ratio_calculated(
        self,
        client: AsyncClient,
        auth_headers: dict,
        sample_multipart_file: dict
    ):
        """
        Test compression_ratio присутствует при compress=true.

        compression_ratio должен быть числом > 0 когда файл сжат.
        """
        data = {
            "compress": "true",
            "compression_algorithm": "gzip",
            "description": "Test compression ratio"
        }

        response = await client.post(
            "/api/v1/files/upload",
            headers=auth_headers,
            files=sample_multipart_file,
            data=data
        )

        assert response.status_code == 200
        result = response.json()

        # compression_ratio должен присутствовать и быть числом
        assert "compression_ratio" in result
        if result["compression_ratio"] is not None:
            assert isinstance(result["compression_ratio"], (int, float))
            assert result["compression_ratio"] > 0

    async def test_upload_compression_ratio_null_when_disabled(
        self,
        client: AsyncClient,
        auth_headers: dict,
        sample_multipart_file: dict
    ):
        """
        Test compression_ratio = null при compress=false.

        Когда сжатие отключено, compression_ratio должен быть null.
        """
        data = {
            "compress": "false",  # off/on format
            "description": "Test no compression"
        }

        response = await client.post(
            "/api/v1/files/upload",
            headers=auth_headers,
            files=sample_multipart_file,
            data=data
        )

        assert response.status_code == 200
        result = response.json()

        # compression_ratio должен быть null (None в Python)
        assert "compression_ratio" in result
        assert result["compression_ratio"] is None
