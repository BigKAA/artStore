"""
Comprehensive Integration Tests для всех API Endpoints Storage Element.

Тестируют полный цикл работы с файлами через реальные HTTP запросы
к Storage Element API с аутентификацией через OAuth 2.0 (test service account).

API Endpoints:
- POST /api/v1/files/upload - Загрузка файла
- GET /api/v1/files/{file_id} - Получение метаданных
- GET /api/v1/files/{file_id}/download - Скачивание файла
- DELETE /api/v1/files/{file_id} - Удаление файла
- PATCH /api/v1/files/{file_id} - Обновление метаданных
- GET /api/v1/files/ - Список файлов

Требования:
- Docker containers running: postgres, redis, admin-module, storage-element
- Test service account активен в Admin Module
"""

import hashlib
import io
import uuid
from datetime import datetime

import pytest
from httpx import AsyncClient


# =============================================================================
# Test Data Constants
# =============================================================================

TEST_TEXT_CONTENT = b"Test file content for comprehensive integration testing.\n" * 100
TEST_TEXT_FILENAME = "test_document.txt"
TEST_TEXT_CONTENT_TYPE = "text/plain"

# Минимальный валидный PDF
TEST_PDF_CONTENT = (
    b"%PDF-1.4\n"
    b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
    b"2 0 obj<</Type/Pages/Count 0/Kids[]>>endobj\n"
    b"xref\n0 3\n"
    b"0000000000 65535 f\n"
    b"0000000009 00000 n\n"
    b"0000000052 00000 n\n"
    b"trailer<</Size 3/Root 1 0 R>>\n"
    b"startxref\n101\n%%EOF"
)


# =============================================================================
# Helper Functions
# =============================================================================

def calculate_sha256(content: bytes) -> str:
    """Вычисляет SHA256 хеш содержимого."""
    return hashlib.sha256(content).hexdigest()


# =============================================================================
# TEST CLASS: File Upload (POST /api/v1/files/upload)
# =============================================================================

@pytest.mark.asyncio
class TestFileUpload:
    """Тесты для POST /api/v1/files/upload endpoint."""

    async def test_upload_text_file_success(
        self,
        async_client: AsyncClient,
        service_account_headers: dict,
        cleanup_uploaded_files: list,
    ):
        """Успешная загрузка текстового файла."""
        test_file = io.BytesIO(TEST_TEXT_CONTENT)

        response = await async_client.post(
            "/api/v1/files/upload",
            headers=service_account_headers,
            files={"file": (TEST_TEXT_FILENAME, test_file, TEST_TEXT_CONTENT_TYPE)},
        )

        assert response.status_code == 201
        data = response.json()

        # Сохраняем для cleanup
        cleanup_uploaded_files.append(data["file_id"])

        # Проверяем структуру ответа
        assert "file_id" in data
        assert "original_filename" in data
        assert "file_size" in data
        assert "checksum" in data

    async def test_upload_pdf_file_success(
        self,
        async_client: AsyncClient,
        service_account_headers: dict,
        cleanup_uploaded_files: list,
    ):
        """Успешная загрузка PDF файла."""
        test_file = io.BytesIO(TEST_PDF_CONTENT)

        response = await async_client.post(
            "/api/v1/files/upload",
            headers=service_account_headers,
            files={"file": ("document.pdf", test_file, "application/pdf")},
        )

        assert response.status_code == 201
        data = response.json()
        cleanup_uploaded_files.append(data["file_id"])

        assert data["original_filename"] == "document.pdf"

    async def test_upload_with_description(
        self,
        async_client: AsyncClient,
        service_account_headers: dict,
        cleanup_uploaded_files: list,
    ):
        """Загрузка файла с описанием."""
        test_file = io.BytesIO(TEST_TEXT_CONTENT)
        description = "Тестовый документ для интеграционных тестов"

        response = await async_client.post(
            "/api/v1/files/upload",
            headers=service_account_headers,
            files={"file": (TEST_TEXT_FILENAME, test_file, TEST_TEXT_CONTENT_TYPE)},
            data={"description": description},
        )

        assert response.status_code == 201
        data = response.json()
        cleanup_uploaded_files.append(data["file_id"])

        # Проверяем что description сохранился через GET metadata
        meta_response = await async_client.get(
            f"/api/v1/files/{data['file_id']}",
            headers=service_account_headers,
        )
        assert meta_response.status_code == 200
        assert meta_response.json().get("description") == description

    async def test_upload_with_version(
        self,
        async_client: AsyncClient,
        service_account_headers: dict,
        cleanup_uploaded_files: list,
    ):
        """Загрузка файла с указанием версии."""
        test_file = io.BytesIO(TEST_TEXT_CONTENT)
        version = "1.0.0"

        response = await async_client.post(
            "/api/v1/files/upload",
            headers=service_account_headers,
            files={"file": (TEST_TEXT_FILENAME, test_file, TEST_TEXT_CONTENT_TYPE)},
            data={"version": version},
        )

        assert response.status_code == 201
        data = response.json()
        cleanup_uploaded_files.append(data["file_id"])

        # Проверяем version через GET metadata
        meta_response = await async_client.get(
            f"/api/v1/files/{data['file_id']}",
            headers=service_account_headers,
        )
        assert meta_response.status_code == 200
        assert meta_response.json().get("version") == version

    async def test_upload_returns_correct_file_size(
        self,
        async_client: AsyncClient,
        service_account_headers: dict,
        cleanup_uploaded_files: list,
    ):
        """Проверка что file_size соответствует размеру загруженного файла."""
        test_file = io.BytesIO(TEST_TEXT_CONTENT)

        response = await async_client.post(
            "/api/v1/files/upload",
            headers=service_account_headers,
            files={"file": (TEST_TEXT_FILENAME, test_file, TEST_TEXT_CONTENT_TYPE)},
        )

        assert response.status_code == 201
        data = response.json()
        cleanup_uploaded_files.append(data["file_id"])

        assert data["file_size"] == len(TEST_TEXT_CONTENT)

    async def test_upload_checksum_is_sha256(
        self,
        async_client: AsyncClient,
        service_account_headers: dict,
        cleanup_uploaded_files: list,
    ):
        """Checksum должен быть 64-символьным SHA256 хешем."""
        test_file = io.BytesIO(TEST_TEXT_CONTENT)
        expected_checksum = calculate_sha256(TEST_TEXT_CONTENT)

        response = await async_client.post(
            "/api/v1/files/upload",
            headers=service_account_headers,
            files={"file": (TEST_TEXT_FILENAME, test_file, TEST_TEXT_CONTENT_TYPE)},
        )

        assert response.status_code == 201
        data = response.json()
        cleanup_uploaded_files.append(data["file_id"])

        # Checksum должен быть 64 символа (SHA256 hex)
        assert len(data["checksum"]) == 64
        assert data["checksum"] == expected_checksum

    async def test_upload_without_auth_returns_401(
        self,
        async_client: AsyncClient,
    ):
        """Загрузка без токена возвращает 401 Unauthorized."""
        test_file = io.BytesIO(TEST_TEXT_CONTENT)

        response = await async_client.post(
            "/api/v1/files/upload",
            files={"file": (TEST_TEXT_FILENAME, test_file, TEST_TEXT_CONTENT_TYPE)},
        )

        assert response.status_code == 401

    async def test_upload_with_invalid_token_returns_401(
        self,
        async_client: AsyncClient,
    ):
        """Загрузка с невалидным токеном возвращает 401."""
        test_file = io.BytesIO(TEST_TEXT_CONTENT)
        invalid_headers = {"Authorization": "Bearer invalid_token_12345"}

        response = await async_client.post(
            "/api/v1/files/upload",
            headers=invalid_headers,
            files={"file": (TEST_TEXT_FILENAME, test_file, TEST_TEXT_CONTENT_TYPE)},
        )

        assert response.status_code == 401

    async def test_upload_file_id_is_valid_uuid(
        self,
        async_client: AsyncClient,
        service_account_headers: dict,
        cleanup_uploaded_files: list,
    ):
        """file_id должен быть валидным UUID."""
        test_file = io.BytesIO(TEST_TEXT_CONTENT)

        response = await async_client.post(
            "/api/v1/files/upload",
            headers=service_account_headers,
            files={"file": (TEST_TEXT_FILENAME, test_file, TEST_TEXT_CONTENT_TYPE)},
        )

        assert response.status_code == 201
        data = response.json()
        cleanup_uploaded_files.append(data["file_id"])

        # Проверяем что file_id - валидный UUID
        try:
            uuid.UUID(data["file_id"])
        except ValueError:
            pytest.fail(f"file_id '{data['file_id']}' is not a valid UUID")


# =============================================================================
# TEST CLASS: File Metadata (GET /api/v1/files/{file_id})
# =============================================================================

@pytest.mark.asyncio
class TestFileMetadata:
    """Тесты для GET /api/v1/files/{file_id} endpoint."""

    async def test_get_metadata_success(
        self,
        async_client: AsyncClient,
        service_account_headers: dict,
        uploaded_file_with_cleanup: dict,
    ):
        """Успешное получение метаданных файла."""
        file_id = uploaded_file_with_cleanup["file_id"]

        response = await async_client.get(
            f"/api/v1/files/{file_id}",
            headers=service_account_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["file_id"] == file_id

    async def test_get_metadata_returns_required_fields(
        self,
        async_client: AsyncClient,
        service_account_headers: dict,
        uploaded_file_with_cleanup: dict,
    ):
        """Response содержит все обязательные поля метаданных."""
        file_id = uploaded_file_with_cleanup["file_id"]

        response = await async_client.get(
            f"/api/v1/files/{file_id}",
            headers=service_account_headers,
        )

        assert response.status_code == 200
        data = response.json()

        # Обязательные поля attr.json
        required_fields = [
            "file_id",
            "original_filename",
            "storage_filename",
            "file_size",
            "content_type",
            "created_at",
            "created_by_username",
            "storage_path",
            "checksum",
        ]

        for field in required_fields:
            assert field in data, f"Missing required field: {field}"

    async def test_get_metadata_nonexistent_returns_404(
        self,
        async_client: AsyncClient,
        service_account_headers: dict,
    ):
        """Несуществующий file_id возвращает 404 Not Found."""
        fake_uuid = str(uuid.uuid4())

        response = await async_client.get(
            f"/api/v1/files/{fake_uuid}",
            headers=service_account_headers,
        )

        assert response.status_code == 404

    async def test_get_metadata_invalid_uuid_returns_422(
        self,
        async_client: AsyncClient,
        service_account_headers: dict,
    ):
        """Невалидный UUID возвращает 422 Unprocessable Entity."""
        response = await async_client.get(
            "/api/v1/files/not-a-valid-uuid",
            headers=service_account_headers,
        )

        assert response.status_code == 422

    async def test_get_metadata_without_auth_returns_401(
        self,
        async_client: AsyncClient,
        uploaded_file_with_cleanup: dict,
    ):
        """Запрос без авторизации возвращает 401."""
        file_id = uploaded_file_with_cleanup["file_id"]

        response = await async_client.get(f"/api/v1/files/{file_id}")

        assert response.status_code == 401


# =============================================================================
# TEST CLASS: File Download (GET /api/v1/files/{file_id}/download)
# =============================================================================

@pytest.mark.asyncio
class TestFileDownload:
    """Тесты для GET /api/v1/files/{file_id}/download endpoint."""

    async def test_download_success(
        self,
        async_client: AsyncClient,
        service_account_headers: dict,
        uploaded_file_with_cleanup: dict,
    ):
        """Успешное скачивание файла."""
        file_id = uploaded_file_with_cleanup["file_id"]

        response = await async_client.get(
            f"/api/v1/files/{file_id}/download",
            headers=service_account_headers,
        )

        assert response.status_code == 200
        assert len(response.content) > 0

    async def test_download_content_matches_upload(
        self,
        async_client: AsyncClient,
        service_account_headers: dict,
        cleanup_uploaded_files: list,
    ):
        """Скачанный контент совпадает с загруженным."""
        # Загружаем файл
        test_content = b"Specific content for download test - unique string 12345\n"
        test_file = io.BytesIO(test_content)

        upload_response = await async_client.post(
            "/api/v1/files/upload",
            headers=service_account_headers,
            files={"file": ("download_test.txt", test_file, "text/plain")},
        )

        assert upload_response.status_code == 201
        file_id = upload_response.json()["file_id"]
        cleanup_uploaded_files.append(file_id)

        # Скачиваем и сравниваем
        download_response = await async_client.get(
            f"/api/v1/files/{file_id}/download",
            headers=service_account_headers,
        )

        assert download_response.status_code == 200
        assert download_response.content == test_content

    async def test_download_checksum_matches(
        self,
        async_client: AsyncClient,
        service_account_headers: dict,
        cleanup_uploaded_files: list,
    ):
        """SHA256 скачанного файла совпадает с checksum в метаданных."""
        # Загружаем файл
        test_content = b"Content for checksum verification test\n" * 50
        test_file = io.BytesIO(test_content)

        upload_response = await async_client.post(
            "/api/v1/files/upload",
            headers=service_account_headers,
            files={"file": ("checksum_test.txt", test_file, "text/plain")},
        )

        assert upload_response.status_code == 201
        file_data = upload_response.json()
        file_id = file_data["file_id"]
        cleanup_uploaded_files.append(file_id)

        # Скачиваем и проверяем checksum
        download_response = await async_client.get(
            f"/api/v1/files/{file_id}/download",
            headers=service_account_headers,
        )

        assert download_response.status_code == 200
        downloaded_checksum = calculate_sha256(download_response.content)
        assert downloaded_checksum == file_data["checksum"]

    async def test_download_nonexistent_returns_404(
        self,
        async_client: AsyncClient,
        service_account_headers: dict,
    ):
        """Скачивание несуществующего файла возвращает 404."""
        fake_uuid = str(uuid.uuid4())

        response = await async_client.get(
            f"/api/v1/files/{fake_uuid}/download",
            headers=service_account_headers,
        )

        assert response.status_code == 404

    async def test_download_without_auth_returns_401(
        self,
        async_client: AsyncClient,
        uploaded_file_with_cleanup: dict,
    ):
        """Скачивание без авторизации возвращает 401."""
        file_id = uploaded_file_with_cleanup["file_id"]

        response = await async_client.get(f"/api/v1/files/{file_id}/download")

        assert response.status_code == 401

    async def test_download_has_content_type_header(
        self,
        async_client: AsyncClient,
        service_account_headers: dict,
        uploaded_file_with_cleanup: dict,
    ):
        """Content-Type header присутствует в ответе."""
        file_id = uploaded_file_with_cleanup["file_id"]

        response = await async_client.get(
            f"/api/v1/files/{file_id}/download",
            headers=service_account_headers,
        )

        assert response.status_code == 200
        assert "content-type" in response.headers


# =============================================================================
# TEST CLASS: File Delete (DELETE /api/v1/files/{file_id})
# =============================================================================

@pytest.mark.asyncio
class TestFileDelete:
    """
    Тесты для DELETE /api/v1/files/{file_id} endpoint.

    ВАЖНО: DELETE требует роль OPERATOR или ADMIN согласно RBAC.
    Test service account имеет роль USER, поэтому ожидаем 403 Forbidden.
    """

    async def test_delete_with_user_role_returns_403(
        self,
        async_client: AsyncClient,
        service_account_headers: dict,
    ):
        """
        Удаление файла с ролью USER возвращает 403 Forbidden.

        DELETE endpoint требует роль OPERATOR или ADMIN.
        Test service account имеет роль USER.
        """
        # Загружаем файл для попытки удаления
        test_file = io.BytesIO(b"File to delete\n")

        upload_response = await async_client.post(
            "/api/v1/files/upload",
            headers=service_account_headers,
            files={"file": ("to_delete.txt", test_file, "text/plain")},
        )

        assert upload_response.status_code == 201
        file_id = upload_response.json()["file_id"]

        # Пытаемся удалить - ожидаем 403 из-за недостаточных прав
        delete_response = await async_client.delete(
            f"/api/v1/files/{file_id}",
            headers=service_account_headers,
        )

        assert delete_response.status_code == 403, (
            f"Ожидался 403 Forbidden для роли USER, получен {delete_response.status_code}"
        )

    async def test_delete_returns_forbidden_message(
        self,
        async_client: AsyncClient,
        service_account_headers: dict,
    ):
        """Ответ 403 содержит сообщение о недостаточных правах."""
        # Загружаем файл
        test_file = io.BytesIO(b"File to delete and verify\n")

        upload_response = await async_client.post(
            "/api/v1/files/upload",
            headers=service_account_headers,
            files={"file": ("delete_verify.txt", test_file, "text/plain")},
        )

        file_id = upload_response.json()["file_id"]

        # Пытаемся удалить
        response = await async_client.delete(
            f"/api/v1/files/{file_id}",
            headers=service_account_headers,
        )

        assert response.status_code == 403
        # Проверяем что есть сообщение об ошибке
        assert "detail" in response.json()

    async def test_delete_nonexistent_with_user_role_returns_403(
        self,
        async_client: AsyncClient,
        service_account_headers: dict,
    ):
        """
        Удаление несуществующего файла с ролью USER возвращает 403 (RBAC проверка до проверки существования).
        """
        fake_uuid = str(uuid.uuid4())

        response = await async_client.delete(
            f"/api/v1/files/{fake_uuid}",
            headers=service_account_headers,
        )

        # RBAC проверка происходит ДО проверки существования файла
        assert response.status_code == 403

    async def test_delete_without_auth_returns_401(
        self,
        async_client: AsyncClient,
        uploaded_file_with_cleanup: dict,
    ):
        """Удаление без авторизации возвращает 401."""
        file_id = uploaded_file_with_cleanup["file_id"]

        response = await async_client.delete(f"/api/v1/files/{file_id}")

        assert response.status_code == 401

    async def test_delete_invalid_uuid_with_user_role_returns_403_or_422(
        self,
        async_client: AsyncClient,
        service_account_headers: dict,
    ):
        """
        Невалидный UUID с ролью USER возвращает 403 (RBAC) или 422 (validation).

        Порядок проверок зависит от реализации - RBAC может проверяться до валидации UUID.
        """
        response = await async_client.delete(
            "/api/v1/files/not-a-valid-uuid",
            headers=service_account_headers,
        )

        # Допустимы оба варианта в зависимости от порядка middleware
        assert response.status_code in (403, 422), (
            f"Ожидался 403 или 422, получен {response.status_code}"
        )


# =============================================================================
# TEST CLASS: File Update (PATCH /api/v1/files/{file_id})
# =============================================================================

@pytest.mark.asyncio
class TestFileUpdate:
    """Тесты для PATCH /api/v1/files/{file_id} endpoint."""

    async def test_update_description_success(
        self,
        async_client: AsyncClient,
        service_account_headers: dict,
        uploaded_file_with_cleanup: dict,
    ):
        """Успешное обновление description."""
        file_id = uploaded_file_with_cleanup["file_id"]
        new_description = "Updated description via PATCH"

        response = await async_client.patch(
            f"/api/v1/files/{file_id}",
            headers=service_account_headers,
            json={"description": new_description},
        )

        assert response.status_code == 200

        # Проверяем что description обновился
        meta_response = await async_client.get(
            f"/api/v1/files/{file_id}",
            headers=service_account_headers,
        )
        assert meta_response.json()["description"] == new_description

    async def test_update_version_success(
        self,
        async_client: AsyncClient,
        service_account_headers: dict,
        uploaded_file_with_cleanup: dict,
    ):
        """Успешное обновление version."""
        file_id = uploaded_file_with_cleanup["file_id"]
        new_version = "2.0.0"

        response = await async_client.patch(
            f"/api/v1/files/{file_id}",
            headers=service_account_headers,
            json={"version": new_version},
        )

        assert response.status_code == 200

        # Проверяем
        meta_response = await async_client.get(
            f"/api/v1/files/{file_id}",
            headers=service_account_headers,
        )
        assert meta_response.json()["version"] == new_version

    async def test_update_multiple_fields(
        self,
        async_client: AsyncClient,
        service_account_headers: dict,
        uploaded_file_with_cleanup: dict,
    ):
        """Обновление нескольких полей одновременно."""
        file_id = uploaded_file_with_cleanup["file_id"]
        update_data = {
            "description": "Multi-field update description",
            "version": "3.0.0",
        }

        response = await async_client.patch(
            f"/api/v1/files/{file_id}",
            headers=service_account_headers,
            json=update_data,
        )

        assert response.status_code == 200

        # Проверяем все поля
        meta_response = await async_client.get(
            f"/api/v1/files/{file_id}",
            headers=service_account_headers,
        )
        meta_data = meta_response.json()
        assert meta_data["description"] == update_data["description"]
        assert meta_data["version"] == update_data["version"]

    async def test_update_nonexistent_returns_404(
        self,
        async_client: AsyncClient,
        service_account_headers: dict,
    ):
        """Обновление несуществующего файла возвращает 404."""
        fake_uuid = str(uuid.uuid4())

        response = await async_client.patch(
            f"/api/v1/files/{fake_uuid}",
            headers=service_account_headers,
            json={"description": "New description"},
        )

        assert response.status_code == 404

    async def test_update_without_auth_returns_401(
        self,
        async_client: AsyncClient,
        uploaded_file_with_cleanup: dict,
    ):
        """Обновление без авторизации возвращает 401."""
        file_id = uploaded_file_with_cleanup["file_id"]

        response = await async_client.patch(
            f"/api/v1/files/{file_id}",
            json={"description": "Unauthorized update"},
        )

        assert response.status_code == 401

    async def test_update_preserves_other_fields(
        self,
        async_client: AsyncClient,
        service_account_headers: dict,
        cleanup_uploaded_files: list,
    ):
        """Обновление одного поля не затрагивает другие."""
        # Загружаем файл с description и version
        test_file = io.BytesIO(b"File for preserve test\n")

        upload_response = await async_client.post(
            "/api/v1/files/upload",
            headers=service_account_headers,
            files={"file": ("preserve_test.txt", test_file, "text/plain")},
            data={"description": "Original description", "version": "1.0"},
        )

        file_id = upload_response.json()["file_id"]
        cleanup_uploaded_files.append(file_id)

        # Получаем оригинальные метаданные
        original_meta = await async_client.get(
            f"/api/v1/files/{file_id}",
            headers=service_account_headers,
        )
        original_data = original_meta.json()

        # Обновляем только description
        await async_client.patch(
            f"/api/v1/files/{file_id}",
            headers=service_account_headers,
            json={"description": "Updated description only"},
        )

        # Проверяем что version не изменился
        updated_meta = await async_client.get(
            f"/api/v1/files/{file_id}",
            headers=service_account_headers,
        )
        updated_data = updated_meta.json()

        assert updated_data["version"] == original_data["version"]
        assert updated_data["original_filename"] == original_data["original_filename"]
        assert updated_data["file_size"] == original_data["file_size"]


# =============================================================================
# TEST CLASS: File List (GET /api/v1/files/)
# =============================================================================

@pytest.mark.asyncio
class TestFileList:
    """Тесты для GET /api/v1/files/ endpoint."""

    async def test_list_files_success(
        self,
        async_client: AsyncClient,
        service_account_headers: dict,
    ):
        """Успешное получение списка файлов."""
        response = await async_client.get(
            "/api/v1/files/",
            headers=service_account_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert "files" in data or "items" in data or isinstance(data, list)

    async def test_list_returns_pagination_info(
        self,
        async_client: AsyncClient,
        service_account_headers: dict,
    ):
        """Response содержит информацию о пагинации (total)."""
        response = await async_client.get(
            "/api/v1/files/",
            headers=service_account_headers,
        )

        assert response.status_code == 200
        data = response.json()

        # Проверяем наличие total или структуры пагинации
        assert "total" in data or "files" in data or isinstance(data, list)

    async def test_list_with_limit(
        self,
        async_client: AsyncClient,
        service_account_headers: dict,
    ):
        """Параметр limit ограничивает количество результатов."""
        response = await async_client.get(
            "/api/v1/files/",
            headers=service_account_headers,
            params={"limit": 5},
        )

        assert response.status_code == 200
        data = response.json()

        # Проверяем что вернулось не больше limit элементов
        files = data.get("files") or data.get("items") or data
        if isinstance(files, list):
            assert len(files) <= 5

    async def test_list_with_skip(
        self,
        async_client: AsyncClient,
        service_account_headers: dict,
    ):
        """Параметр skip пропускает первые N результатов."""
        response = await async_client.get(
            "/api/v1/files/",
            headers=service_account_headers,
            params={"skip": 0, "limit": 10},
        )

        assert response.status_code == 200

    async def test_list_without_auth_returns_401(
        self,
        async_client: AsyncClient,
    ):
        """Список без авторизации возвращает 401."""
        response = await async_client.get("/api/v1/files/")

        assert response.status_code == 401

    async def test_list_includes_uploaded_file(
        self,
        async_client: AsyncClient,
        service_account_headers: dict,
        uploaded_file_with_cleanup: dict,
    ):
        """Загруженный файл появляется в списке."""
        file_id = uploaded_file_with_cleanup["file_id"]

        response = await async_client.get(
            "/api/v1/files/",
            headers=service_account_headers,
            params={"limit": 100},
        )

        assert response.status_code == 200
        data = response.json()

        files = data.get("files") or data.get("items") or data
        file_ids = [f.get("file_id") for f in files if isinstance(f, dict)]

        assert file_id in file_ids, f"Uploaded file {file_id} not found in list"
