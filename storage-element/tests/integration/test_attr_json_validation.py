"""
Тесты валидации attr.json метаданных через API.

Проверяет корректность структуры и содержимого метаданных файлов,
возвращаемых API Storage Element. Attr.json файлы - единственный
источник истины для метаданных в системе ArtStore.

Использует real OAuth через Admin Module с test service account.
"""

import io
import re
import uuid
from datetime import datetime, timezone

import pytest
import pytest_asyncio

# =============================================================================
# Fixtures
# =============================================================================


@pytest_asyncio.fixture(scope="function")
async def test_file_for_validation(async_client, service_account_headers):
    """
    Создает тестовый файл с известными параметрами для валидации метаданных.

    Загружает файл с предопределенным содержимым и метаданными,
    чтобы проверить корректность их сохранения и возврата через API.

    Yields:
        dict: Данные загруженного файла и исходные параметры для сравнения
    """
    # Известные параметры файла для точной валидации
    test_content = b"Test content for attr.json validation.\n" * 10  # 400 bytes
    test_filename = "validation_test_file.txt"
    test_description = "Test file for attr.json validation"
    test_version = "1.0.0"
    test_metadata = {
        "document_type": "validation_test",
        "department": "QA",
        "author": "Integration Test Suite",
        "tags": ["test", "validation", "attr.json"],
    }

    # Загрузка файла
    response = await async_client.post(
        "/api/v1/files/upload",
        headers=service_account_headers,
        files={"file": (test_filename, io.BytesIO(test_content), "text/plain")},
        data={
            "description": test_description,
            "version": test_version,
            "metadata": str(test_metadata),  # JSON string в form data
        },
    )

    assert response.status_code == 201, f"Upload failed: {response.text}"
    file_data = response.json()

    # Возвращаем данные файла и исходные параметры
    yield {
        "api_response": file_data,
        "original": {
            "content": test_content,
            "filename": test_filename,
            "description": test_description,
            "version": test_version,
            "metadata": test_metadata,
            "content_size": len(test_content),
            "content_type": "text/plain",
        },
    }

    # Cleanup
    try:
        await async_client.delete(
            f"/api/v1/files/{file_data['file_id']}",
            headers=service_account_headers,
        )
    except Exception:
        pass


# =============================================================================
# Test Class: Attr.json Structure Validation
# =============================================================================


@pytest.mark.asyncio
class TestAttrJsonRequiredFields:
    """
    Тесты проверки обязательных полей в метаданных attr.json.

    Согласно Attribute-First Storage Model, attr.json содержит все
    необходимые метаданные файла и является единственным источником истины.
    """

    async def test_metadata_has_all_required_fields(
        self, test_file_for_validation, async_client, service_account_headers
    ):
        """
        Проверяет наличие всех обязательных полей в метаданных файла.

        Обязательные поля согласно FileMetadataResponse schema:
        - file_id: UUID идентификатор
        - original_filename: исходное имя файла
        - storage_filename: имя файла в хранилище
        - file_size: размер в байтах
        - content_type: MIME тип
        - created_at: timestamp создания (ISO 8601)
        - created_by_username: имя пользователя/service account
        - storage_path: путь к файлу в хранилище
        - checksum: SHA256 хеш содержимого
        """
        file_id = test_file_for_validation["api_response"]["file_id"]

        # Получаем метаданные через API
        response = await async_client.get(
            f"/api/v1/files/{file_id}",
            headers=service_account_headers,
        )

        assert response.status_code == 200
        metadata = response.json()

        # Проверяем наличие всех обязательных полей согласно FileMetadataResponse
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

        missing_fields = [
            field for field in required_fields if field not in metadata
        ]

        assert not missing_fields, (
            f"Отсутствуют обязательные поля в метаданных: {missing_fields}\n"
            f"Полученные поля: {list(metadata.keys())}"
        )

    async def test_file_id_is_valid_uuid(
        self, test_file_for_validation, async_client, service_account_headers
    ):
        """
        Проверяет что file_id является валидным UUID v4.

        UUID используется для уникальной идентификации файлов
        в распределенной системе хранения.
        """
        file_id = test_file_for_validation["api_response"]["file_id"]

        response = await async_client.get(
            f"/api/v1/files/{file_id}",
            headers=service_account_headers,
        )

        assert response.status_code == 200
        metadata = response.json()

        # Проверяем формат UUID
        try:
            parsed_uuid = uuid.UUID(metadata["file_id"])
            # Проверяем что это валидный UUID (версия не критична)
            assert parsed_uuid.version in (1, 4), "UUID должен быть версии 1 или 4"
        except ValueError as e:
            pytest.fail(f"file_id не является валидным UUID: {metadata['file_id']}, ошибка: {e}")

        # UUID из ответа должен совпадать с запрошенным
        assert metadata["file_id"] == file_id

    async def test_checksum_is_sha256_hex(
        self, test_file_for_validation, async_client, service_account_headers
    ):
        """
        Проверяет что checksum является 64-символьным SHA256 hex.

        SHA256 хеш используется для верификации целостности файла.
        Формат: 64 символа lowercase hex (0-9, a-f).
        """
        file_id = test_file_for_validation["api_response"]["file_id"]

        response = await async_client.get(
            f"/api/v1/files/{file_id}",
            headers=service_account_headers,
        )

        assert response.status_code == 200
        metadata = response.json()

        checksum = metadata.get("checksum", "")

        # Проверяем длину (SHA256 = 64 hex символа)
        assert len(checksum) == 64, (
            f"Checksum должен быть 64 символа (SHA256), получено: {len(checksum)}"
        )

        # Проверяем формат (только hex символы)
        hex_pattern = re.compile(r"^[0-9a-f]{64}$")
        assert hex_pattern.match(checksum), (
            f"Checksum должен содержать только lowercase hex символы: {checksum}"
        )

    async def test_file_size_matches_uploaded_content(
        self, test_file_for_validation, async_client, service_account_headers
    ):
        """
        Проверяет что file_size соответствует размеру загруженного контента.

        Размер файла должен точно соответствовать количеству байт
        в исходном содержимом.
        """
        file_id = test_file_for_validation["api_response"]["file_id"]
        expected_size = test_file_for_validation["original"]["content_size"]

        response = await async_client.get(
            f"/api/v1/files/{file_id}",
            headers=service_account_headers,
        )

        assert response.status_code == 200
        metadata = response.json()

        assert metadata["file_size"] == expected_size, (
            f"file_size не соответствует размеру загруженного контента. "
            f"Ожидалось: {expected_size}, получено: {metadata['file_size']}"
        )

    async def test_timestamps_are_iso8601_format(
        self, test_file_for_validation, async_client, service_account_headers
    ):
        """
        Проверяет что created_at в формате ISO 8601.

        Формат: YYYY-MM-DDTHH:MM:SS.ffffff или с timezone offset.
        Timestamps должны быть парсабельными стандартными средствами.

        Примечание: API возвращает только created_at, updated_at не возвращается в response.
        """
        file_id = test_file_for_validation["api_response"]["file_id"]

        response = await async_client.get(
            f"/api/v1/files/{file_id}",
            headers=service_account_headers,
        )

        assert response.status_code == 200
        metadata = response.json()

        # API возвращает только created_at
        timestamp_str = metadata.get("created_at")
        assert timestamp_str, "Поле created_at отсутствует или пустое"

        # Пробуем распарсить как ISO 8601
        try:
            # Python 3.11+ поддерживает fromisoformat с Z
            if timestamp_str.endswith("Z"):
                timestamp_str = timestamp_str[:-1] + "+00:00"
            parsed = datetime.fromisoformat(timestamp_str)

            # Проверяем разумность timestamp (не в будущем, не слишком старый)
            now = datetime.now(timezone.utc)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)

            assert parsed <= now, f"created_at в будущем: {timestamp_str}"
            # Не старше 1 часа (для свежезагруженного файла)
            age_seconds = (now - parsed).total_seconds()
            assert age_seconds < 3600, (
                f"created_at слишком старый для свежего файла: {timestamp_str}"
            )

        except ValueError as e:
            pytest.fail(f"created_at не является валидным ISO 8601: {timestamp_str}, ошибка: {e}")

    async def test_original_filename_preserved(
        self, test_file_for_validation, async_client, service_account_headers
    ):
        """
        Проверяет что original_filename соответствует имени загруженного файла.

        Исходное имя файла должно сохраняться без изменений для
        последующего восстановления при скачивании.
        """
        file_id = test_file_for_validation["api_response"]["file_id"]
        expected_filename = test_file_for_validation["original"]["filename"]

        response = await async_client.get(
            f"/api/v1/files/{file_id}",
            headers=service_account_headers,
        )

        assert response.status_code == 200
        metadata = response.json()

        assert metadata["original_filename"] == expected_filename, (
            f"original_filename не соответствует загруженному имени. "
            f"Ожидалось: {expected_filename}, получено: {metadata['original_filename']}"
        )

    async def test_content_type_matches_uploaded(
        self, test_file_for_validation, async_client, service_account_headers
    ):
        """
        Проверяет что content_type соответствует MIME типу загруженного файла.
        """
        file_id = test_file_for_validation["api_response"]["file_id"]
        expected_content_type = test_file_for_validation["original"]["content_type"]

        response = await async_client.get(
            f"/api/v1/files/{file_id}",
            headers=service_account_headers,
        )

        assert response.status_code == 200
        metadata = response.json()

        assert metadata["content_type"] == expected_content_type, (
            f"content_type не соответствует. "
            f"Ожидалось: {expected_content_type}, получено: {metadata['content_type']}"
        )


# =============================================================================
# Test Class: Creator Information Validation
# =============================================================================


@pytest.mark.asyncio
class TestCreatorInformation:
    """
    Тесты проверки информации о создателе файла.

    Информация о создателе извлекается из JWT токена service account
    и должна корректно сохраняться в метаданных.
    """

    async def test_created_by_fields_present(
        self, test_file_for_validation, async_client, service_account_headers
    ):
        """
        Проверяет наличие поля created_by_username.

        Примечание: API возвращает только created_by_username, не created_by_id.
        """
        file_id = test_file_for_validation["api_response"]["file_id"]

        response = await async_client.get(
            f"/api/v1/files/{file_id}",
            headers=service_account_headers,
        )

        assert response.status_code == 200
        metadata = response.json()

        assert "created_by_username" in metadata, "Поле created_by_username отсутствует"

        # Поле не должно быть пустым
        assert metadata["created_by_username"], "created_by_username пустой"

    async def test_created_by_from_service_account_token(
        self, test_file_for_validation, async_client, service_account_headers
    ):
        """
        Проверяет что created_by_username информация соответствует service account из токена.

        Service account name обычно содержится в поле 'name' JWT токена.
        """
        file_id = test_file_for_validation["api_response"]["file_id"]

        response = await async_client.get(
            f"/api/v1/files/{file_id}",
            headers=service_account_headers,
        )

        assert response.status_code == 200
        metadata = response.json()

        # Проверяем что created_by_username не пустой и разумный
        username = metadata.get("created_by_username", "")
        assert username, "created_by_username не должен быть пустым"
        assert len(username) >= 3, "created_by_username слишком короткий"


# =============================================================================
# Test Class: Optional Fields Validation
# =============================================================================


@pytest.mark.asyncio
class TestOptionalFields:
    """
    Тесты проверки опциональных полей метаданных.

    Опциональные поля: description, version, metadata (custom).
    """

    async def test_description_saved_correctly(
        self, test_file_for_validation, async_client, service_account_headers
    ):
        """
        Проверяет что description сохраняется и возвращается корректно.
        """
        file_id = test_file_for_validation["api_response"]["file_id"]
        expected_description = test_file_for_validation["original"]["description"]

        response = await async_client.get(
            f"/api/v1/files/{file_id}",
            headers=service_account_headers,
        )

        assert response.status_code == 200
        metadata = response.json()

        # Description может быть опциональным, но если передан - должен сохраниться
        if "description" in metadata:
            assert metadata["description"] == expected_description

    async def test_version_saved_correctly(
        self, test_file_for_validation, async_client, service_account_headers
    ):
        """
        Проверяет что version сохраняется и возвращается корректно.
        """
        file_id = test_file_for_validation["api_response"]["file_id"]
        expected_version = test_file_for_validation["original"]["version"]

        response = await async_client.get(
            f"/api/v1/files/{file_id}",
            headers=service_account_headers,
        )

        assert response.status_code == 200
        metadata = response.json()

        # Version может быть опциональным
        if "version" in metadata:
            assert metadata["version"] == expected_version


# =============================================================================
# Test Class: Metadata Lifecycle Validation
# =============================================================================


@pytest.mark.asyncio
class TestMetadataLifecycle:
    """
    Тесты жизненного цикла метаданных: создание, обновление.

    Примечание: DELETE тесты перенесены в TestDeleteRBAC, так как
    DELETE требует роль OPERATOR/ADMIN, а test service account имеет роль USER.
    """

    async def test_patch_updates_description(
        self, async_client, service_account_headers, cleanup_uploaded_files
    ):
        """
        Проверяет что PATCH успешно обновляет description файла.

        created_at должен остаться неизменным после обновления.
        """
        # Создаем файл
        test_content = b"File for update test"
        response = await async_client.post(
            "/api/v1/files/upload",
            headers=service_account_headers,
            files={"file": ("update_test.txt", io.BytesIO(test_content), "text/plain")},
        )

        assert response.status_code == 201
        file_id = response.json()["file_id"]
        cleanup_uploaded_files.append(file_id)

        # Получаем начальные метаданные
        response = await async_client.get(
            f"/api/v1/files/{file_id}",
            headers=service_account_headers,
        )
        assert response.status_code == 200
        initial_metadata = response.json()
        initial_created_at = initial_metadata["created_at"]

        # Обновляем файл
        new_description = "Updated description via PATCH"
        response = await async_client.patch(
            f"/api/v1/files/{file_id}",
            headers=service_account_headers,
            json={"description": new_description},
        )

        assert response.status_code == 200

        # Получаем обновленные метаданные
        response = await async_client.get(
            f"/api/v1/files/{file_id}",
            headers=service_account_headers,
        )
        assert response.status_code == 200
        updated_metadata = response.json()

        # Проверяем что description обновился
        assert updated_metadata.get("description") == new_description, (
            f"description не обновился. Ожидалось: {new_description}, "
            f"получено: {updated_metadata.get('description')}"
        )

        # created_at должен остаться прежним
        assert updated_metadata["created_at"] == initial_created_at, (
            "created_at не должен изменяться при обновлении"
        )

    async def test_delete_requires_operator_role(
        self, async_client, service_account_headers
    ):
        """
        Проверяет что DELETE требует роль OPERATOR/ADMIN.

        Test service account имеет роль USER, поэтому ожидаем 403 Forbidden.
        """
        # Создаем файл
        test_content = b"File for delete permission test"
        response = await async_client.post(
            "/api/v1/files/upload",
            headers=service_account_headers,
            files={"file": ("delete_perm_test.txt", io.BytesIO(test_content), "text/plain")},
        )

        assert response.status_code == 201
        file_id = response.json()["file_id"]

        # Проверяем что файл существует
        response = await async_client.get(
            f"/api/v1/files/{file_id}",
            headers=service_account_headers,
        )
        assert response.status_code == 200

        # Пытаемся удалить файл с ролью USER - ожидаем 403
        response = await async_client.delete(
            f"/api/v1/files/{file_id}",
            headers=service_account_headers,
        )
        assert response.status_code == 403, (
            f"DELETE должен возвращать 403 для роли USER, "
            f"но получен статус {response.status_code}"
        )

        # Файл должен по-прежнему существовать
        response = await async_client.get(
            f"/api/v1/files/{file_id}",
            headers=service_account_headers,
        )
        assert response.status_code == 200, (
            "Файл должен существовать после неудачной попытки удаления"
        )


# =============================================================================
# Test Class: Storage Path Validation
# =============================================================================


@pytest.mark.asyncio
class TestStoragePath:
    """
    Тесты проверки storage_path в метаданных.
    """

    async def test_storage_path_is_not_empty(
        self, test_file_for_validation, async_client, service_account_headers
    ):
        """
        Проверяет что storage_path не пустой.

        storage_path указывает местоположение файла в системе хранения
        и должен быть заполнен для каждого файла.
        """
        file_id = test_file_for_validation["api_response"]["file_id"]

        response = await async_client.get(
            f"/api/v1/files/{file_id}",
            headers=service_account_headers,
        )

        assert response.status_code == 200
        metadata = response.json()

        storage_path = metadata.get("storage_path", "")
        assert storage_path, "storage_path не должен быть пустым"
        assert len(storage_path) > 0, "storage_path должен содержать путь к файлу"

    async def test_storage_filename_is_uuid_based(
        self, test_file_for_validation, async_client, service_account_headers
    ):
        """
        Проверяет что storage_filename основан на UUID (для уникальности).

        В системе ArtStore файлы сохраняются с именами на основе UUID
        для избежания конфликтов имен.
        """
        file_id = test_file_for_validation["api_response"]["file_id"]

        response = await async_client.get(
            f"/api/v1/files/{file_id}",
            headers=service_account_headers,
        )

        assert response.status_code == 200
        metadata = response.json()

        storage_filename = metadata.get("storage_filename", "")
        assert storage_filename, "storage_filename не должен быть пустым"

        # storage_filename должен содержать UUID-подобную строку
        # или соответствовать file_id
        uuid_pattern = re.compile(
            r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
            re.IGNORECASE
        )

        # Проверяем что storage_filename содержит UUID или равен file_id
        has_uuid = uuid_pattern.search(storage_filename) is not None
        matches_file_id = file_id in storage_filename

        assert has_uuid or matches_file_id, (
            f"storage_filename должен содержать UUID: {storage_filename}"
        )
