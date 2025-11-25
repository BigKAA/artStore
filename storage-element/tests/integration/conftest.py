"""
Pytest Configuration для Integration Tests.

Fixtures и настройка для интеграционного тестирования
с реальными сервисами (PostgreSQL, Redis, Storage Element API).
"""

import os
from pathlib import Path

import pytest
from httpx import AsyncClient

# ВАЖНО: Установить JWT_PUBLIC_KEY_PATH ДО импорта app modules
project_root = Path(__file__).parent.parent.parent.parent
public_key_path = project_root / "admin-module" / ".keys" / "public_key.pem"

# Проверка что ключ существует
if not public_key_path.exists():
    raise FileNotFoundError(
        f"JWT public key not found at {public_key_path}. "
        "Ensure admin-module JWT keys are generated."
    )

os.environ["JWT_PUBLIC_KEY_PATH"] = str(public_key_path)

# Настройки для integration tests (ОБЯЗАТЕЛЬНО установить ДО импортов app)
# Используем прямое присваивание чтобы гарантировать что тестовые значения используются
os.environ["DB_HOST"] = "localhost"
os.environ["DB_PORT"] = "5433"
os.environ["DB_USERNAME"] = "artstore_test"
os.environ["DB_PASSWORD"] = "test_password"
os.environ["DB_DATABASE"] = "artstore_test"
os.environ["DB_TABLE_PREFIX"] = "test_storage"  # CRITICAL: Must match Alembic migrations!
os.environ["REDIS_HOST"] = "localhost"
os.environ["REDIS_PORT"] = "6380"
os.environ["LOG_LEVEL"] = "DEBUG"

# CRITICAL: Force reload settings module IMMEDIATELY after setting env vars
# This ensures that when models are imported, settings.database.table_prefix is correct
import sys
import importlib

# Remove cached config module to force reload with new environment variables
if 'app.core.config' in sys.modules:
    del sys.modules['app.core.config']

# Now when app modules import settings, they will get the test configuration
# This must happen BEFORE any pytest fixtures import app modules


@pytest.fixture(scope="session")
def test_environment_info():
    """
    Информация о тестовом окружении для debugging.

    Returns:
        dict: Конфигурация тестового окружения
    """
    return {
        "db_host": os.environ.get("DB_HOST"),
        "db_port": os.environ.get("DB_PORT"),
        "db_database": os.environ.get("DB_DATABASE"),
        "redis_host": os.environ.get("REDIS_HOST"),
        "redis_port": os.environ.get("REDIS_PORT"),
        "jwt_public_key": os.environ.get("JWT_PUBLIC_KEY_PATH"),
        "storage_api_url": os.environ.get("STORAGE_API_URL", "http://localhost:8011"),
    }


@pytest.fixture(scope="function")
def auth_headers():
    """
    Authentication headers с реальными JWT токенами для integration tests.

    ВАЖНО: scope="function" - токен генерируется для каждого теста,
    чтобы избежать expiration issues при длительных test runs.

    Returns:
        dict: HTTP headers с Authorization Bearer токеном

    Примеры:
        >>> async def test_upload_file(auth_headers):
        ...     async with AsyncClient(
        ...         transport=ASGITransport(app=app),
        ...         base_url="http://test"
        ...     ) as client:
        ...         response = await client.post(
        ...             "/api/v1/files/upload",
        ...             headers=auth_headers,
        ...             files={"file": file_content}
        ...         )
    """
    from tests.utils.jwt_utils import create_auth_headers

    return create_auth_headers(
        username="integration_test_user",
        email="integration@test.artstore.local",
        role="admin",
        user_id="integration_test_id"
    )


@pytest.fixture(scope="function")
async def async_client():
    """
    AsyncClient для тестирования API endpoints через real HTTP requests.

    ВАЖНО: Использует real HTTP requests к Docker container на localhost:8010.
    Это обеспечивает true integration testing с правильной конфигурацией.

    Yields:
        AsyncClient: Настроенный async HTTP client

    Примеры:
        >>> async def test_health_check(async_client):
        ...     response = await async_client.get("/health/live")
        ...     assert response.status_code == 200
    """
    # Real HTTP requests к Docker container
    # Порт 8010 - стандартный порт Storage Element в docker-compose.yml
    base_url = os.environ.get("STORAGE_API_URL", "http://localhost:8010")

    async with AsyncClient(
        base_url=base_url,
        timeout=30.0
    ) as client:
        yield client


@pytest.fixture(scope="session")
def test_file_content():
    """
    Тестовое содержимое файла для upload tests.

    Returns:
        bytes: Бинарное содержимое тестового файла
    """
    return b"Test file content for integration testing.\nThis is line 2.\n"


@pytest.fixture(scope="session")
def test_file_metadata():
    """
    Метаданные тестового файла.

    Returns:
        dict: Template-based метаданные для тестового файла
    """
    return {
        "document_type": "test_document",
        "department": "Engineering",
        "author": "Integration Test Suite",
        "tags": ["test", "integration", "automated"],
        "retention_years": 3,
    }


@pytest.fixture(scope="function")
async def cleanup_test_files(async_client, auth_headers):
    """
    Fixture для автоматической очистки файлов после тестов.

    Usage:
        >>> async def test_upload(cleanup_test_files, async_client, auth_headers):
        ...     # Upload file
        ...     response = await async_client.post("/api/v1/files/upload", ...)
        ...     file_id = response.json()["file_id"]
        ...     cleanup_test_files.append(file_id)
        ...     # Test logic...
        ...     # File will be automatically deleted after test

    Yields:
        list: List для добавления file_id файлов для очистки
    """
    files_to_cleanup = []

    yield files_to_cleanup

    # Cleanup после теста
    for file_id in files_to_cleanup:
        try:
            await async_client.delete(
                f"/api/v1/files/{file_id}",
                headers=auth_headers
            )
        except Exception:
            # Игнорируем ошибки при cleanup
            pass


@pytest.fixture(scope="session", autouse=True)
def verify_test_environment():
    """
    Автоматическая проверка тестового окружения перед запуском tests.

    Проверяет:
    - JWT public key существует
    - Environment variables установлены
    - Тестовая БД доступна (опционально)
    - RELOAD settings после установки environment variables

    Raises:
        RuntimeError: Если тестовое окружение не готово
    """
    # CRITICAL: Перезагрузить settings ПОСЛЕ установки environment variables
    # Без этого settings будет использовать default values из config.py
    import importlib
    import sys

    # Удалить закешированные settings modules
    modules_to_reload = [
        'app.core.config',
        'app.db.session',
        'app.models.file_metadata',
        'app.models.storage_config',
        'app.models.wal',
    ]

    for module_name in modules_to_reload:
        if module_name in sys.modules:
            importlib.reload(sys.modules[module_name])

    # Проверка JWT ключа
    jwt_key_path = os.environ.get("JWT_PUBLIC_KEY_PATH")
    if not jwt_key_path or not Path(jwt_key_path).exists():
        raise RuntimeError(
            f"JWT public key not found. Expected at: {jwt_key_path}\n"
            "Ensure admin-module JWT keys are generated:\n"
            "  cd admin-module && python scripts/generate_jwt_keys.py"
        )

    # Проверка обязательных environment variables
    required_vars = [
        "DB_HOST", "DB_PORT", "DB_USERNAME", "DB_PASSWORD", "DB_DATABASE",
        "DB_TABLE_PREFIX",  # CRITICAL for integration tests
        "REDIS_HOST", "REDIS_PORT"
    ]

    missing_vars = [var for var in required_vars if not os.environ.get(var)]
    if missing_vars:
        raise RuntimeError(
            f"Missing required environment variables: {', '.join(missing_vars)}\n"
            "Ensure test environment is properly configured.\n"
            "Run: ./scripts/run_integration_tests.sh"
        )

    # Verify table prefix matches test database
    from app.core.config import settings
    expected_prefix = "test_storage"
    actual_prefix = settings.database.table_prefix

    if actual_prefix != expected_prefix:
        raise RuntimeError(
            f"Table prefix mismatch!\n"
            f"Expected: {expected_prefix}\n"
            f"Actual: {actual_prefix}\n"
            f"Settings not reloaded correctly. Check conftest.py setup."
        )

    print("\n" + "="*60)
    print("Integration Test Environment Configuration:")
    print("="*60)
    print(f"Database: {os.environ.get('DB_USERNAME')}@{os.environ.get('DB_HOST')}:{os.environ.get('DB_PORT')}/{os.environ.get('DB_DATABASE')}")
    print(f"Table Prefix: {settings.database.table_prefix} (verified)")
    print(f"Redis: {os.environ.get('REDIS_HOST')}:{os.environ.get('REDIS_PORT')}")
    print(f"JWT Key: {jwt_key_path}")
    print(f"Storage API: {os.environ.get('STORAGE_API_URL', 'N/A')}")
    print("="*60 + "\n")


# =============================================================================
# Real OAuth Fixtures (через Admin Module с test service account)
# =============================================================================

import pytest_asyncio
from tests.utils.service_account_auth import (
    get_sync_service_account_token,
    create_auth_headers as sa_create_auth_headers,
)


@pytest.fixture(scope="module")
def service_account_token():
    """
    Real OAuth token от test service account через Admin Module.

    Использует OAuth 2.0 Client Credentials flow для получения
    реального JWT токена. Требует запущенный Admin Module.

    Scope: module - токен переиспользуется в рамках модуля тестов.
    Используем синхронную версию для избежания проблем с event_loop scope.

    Returns:
        str: JWT access token от Admin Module

    Raises:
        httpx.HTTPStatusError: Если Admin Module недоступен или credentials неверные
    """
    return get_sync_service_account_token()


@pytest.fixture(scope="module")
def service_account_headers(service_account_token):
    """
    Auth headers с real OAuth token от service account.

    Для тестов требующих реальную аутентификацию через Admin Module.

    Args:
        service_account_token: JWT token из service_account_token fixture

    Returns:
        dict: HTTP headers с Authorization Bearer токеном
    """
    return sa_create_auth_headers(service_account_token)


@pytest_asyncio.fixture(scope="function")
async def uploaded_file_with_cleanup(async_client, service_account_headers):
    """
    Загруженный файл с автоматической очисткой после теста.

    Создает тестовый файл через API и удаляет его после завершения теста.
    Использует real OAuth через service account.

    Yields:
        dict: Response от upload endpoint с file_id, checksum, и т.д.
    """
    import io

    test_content = b"Test file for integration testing with service account.\n" * 50
    test_file = io.BytesIO(test_content)

    response = await async_client.post(
        "/api/v1/files/upload",
        headers=service_account_headers,
        files={"file": ("test_sa_file.txt", test_file, "text/plain")},
        data={"description": "Integration test file with service account"},
    )

    assert response.status_code == 201, f"Upload failed: {response.text}"
    file_data = response.json()

    yield file_data

    # Cleanup
    try:
        await async_client.delete(
            f"/api/v1/files/{file_data['file_id']}",
            headers=service_account_headers,
        )
    except Exception:
        pass  # Игнорируем ошибки cleanup


@pytest_asyncio.fixture(scope="function")
async def cleanup_uploaded_files(async_client, service_account_headers):
    """
    Fixture для автоматической очистки файлов после теста.

    Использует real OAuth через service account.

    Usage:
        >>> async def test_multiple_uploads(cleanup_uploaded_files, async_client, service_account_headers):
        ...     response = await async_client.post("/api/v1/files/upload", ...)
        ...     cleanup_uploaded_files.append(response.json()["file_id"])
        ...     # Test logic...
        ...     # Files will be automatically deleted after test

    Yields:
        list: List для добавления file_id файлов для очистки
    """
    files_to_cleanup = []

    yield files_to_cleanup

    for file_id in files_to_cleanup:
        try:
            await async_client.delete(
                f"/api/v1/files/{file_id}",
                headers=service_account_headers,
            )
        except Exception:
            pass
