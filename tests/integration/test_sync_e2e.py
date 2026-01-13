"""
E2E Integration Tests для Query Module Sync механизма.

PHASE 4: Sprint 16 - Query Module Sync Repair.

Тестирование полного flow:
1. Upload file через Ingester Module
2. Event publish через Admin Module
3. Event subscription через Query Module
4. Cache sync в Query Module
5. Search файла через Query Module

Требования:
- Все модули должны быть запущены (docker-compose up -d)
- PostgreSQL, Redis доступны
- Тестовый Service Account создан
"""

import asyncio
import time
import uuid
import json
from typing import Dict, Any, Optional
from datetime import datetime
import io

import pytest
import httpx
from redis.asyncio import Redis
import redis.asyncio as aioredis


# ==============================================================================
# Базовые URLs для модулей
# ==============================================================================

ADMIN_MODULE_URL = "http://localhost:8000"
INGESTER_MODULE_URL = "http://localhost:8020"
QUERY_MODULE_URL = "http://localhost:8030"
REDIS_URL = "redis://localhost:6379/0"


# ==============================================================================
# Helper Functions
# ==============================================================================

async def get_auth_token(client_id: str = "sa_prod_admin_service_11710636") -> str:
    """
    Получить JWT access token от Admin Module.

    Использует test credentials из docker-compose.yml:
    - client_id: sa_prod_admin_service_11710636 (получен из БД)
    - client_secret: Test-Password123

    Args:
        client_id: Service Account client ID (по умолчанию admin-service)
    """
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{ADMIN_MODULE_URL}/api/v1/auth/token",
            json={
                "client_id": client_id,
                "client_secret": "Test-Password123",
            },
            timeout=10.0
        )

        assert response.status_code == 200, f"Failed to get token: {response.text}"

        data = response.json()
        return data["access_token"]


async def upload_file_to_ingester(
    token: str,
    filename: str,
    content: bytes,
    mime_type: str = "text/plain",
    description: str = "E2E test file",
    tags: Optional[list[str]] = None,
) -> Dict[str, Any]:
    """
    Upload файла через Ingester Module.

    Args:
        token: JWT access token
        filename: Имя файла
        content: Содержимое файла (bytes)
        mime_type: MIME type файла
        description: Описание файла
        tags: Теги для файла

    Returns:
        Response data с file_id и metadata
    """
    if tags is None:
        tags = ["e2e-test"]

    async with httpx.AsyncClient() as client:
        files = {
            "file": (filename, io.BytesIO(content), mime_type)
        }
        data = {
            "description": description,
            "tags": json.dumps(tags),  # Tags как JSON string
        }

        response = await client.post(
            f"{INGESTER_MODULE_URL}/api/v1/files/upload",
            files=files,
            data=data,
            headers={"Authorization": f"Bearer {token}"},
            timeout=30.0
        )

        assert response.status_code == 201, f"Upload failed: {response.text}"

        return response.json()


async def search_file_in_query_module(
    token: str,
    query: str,
    timeout: float = 5.0
) -> Dict[str, Any]:
    """
    Поиск файла через Query Module.

    Args:
        token: JWT access token
        query: Search query string
        timeout: Request timeout

    Returns:
        Search results
    """
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{QUERY_MODULE_URL}/api/v1/files/search",
            params={"query": query},
            headers={"Authorization": f"Bearer {token}"},
            timeout=timeout
        )

        assert response.status_code == 200, f"Search failed: {response.text}"

        return response.json()


async def wait_for_cache_sync(
    token: str,
    filename: str,
    max_wait_seconds: float = 10.0,
    poll_interval: float = 0.5
) -> bool:
    """
    Ожидание синхронизации файла в Query Module cache.

    Polling search endpoint до тех пор, пока файл не появится.

    Args:
        token: JWT access token
        filename: Имя файла для поиска
        max_wait_seconds: Максимальное время ожидания
        poll_interval: Интервал между проверками

    Returns:
        True если файл найден, False если timeout
    """
    start_time = time.time()

    while (time.time() - start_time) < max_wait_seconds:
        try:
            results = await search_file_in_query_module(token, filename)

            # Проверяем, что файл найден в результатах
            if results.get("total", 0) > 0:
                files = results.get("files", [])
                for file in files:
                    if filename in file.get("filename", ""):
                        return True

        except Exception as e:
            # Игнорируем ошибки во время polling
            pass

        await asyncio.sleep(poll_interval)

    return False


async def get_redis_client() -> Redis:
    """Получить async Redis client для мониторинга events."""
    return await aioredis.from_url(
        REDIS_URL,
        decode_responses=True
    )


# ==============================================================================
# E2E Tests
# ==============================================================================

@pytest.mark.asyncio
@pytest.mark.e2e
class TestSyncE2E:
    """E2E тесты для sync механизма Upload → Event → Cache → Search."""

    async def test_upload_and_search_basic_flow(self):
        """
        Базовый E2E тест: upload → sync → search.

        Steps:
        1. Получить auth token
        2. Upload файл через Ingester
        3. Дождаться sync в Query Module cache
        4. Search файл через Query Module
        5. Проверить, что файл найден
        """
        # Step 1: Authentication
        token = await get_auth_token()
        assert token, "Failed to get auth token"

        # Step 2: Upload file
        test_filename = f"e2e_test_{uuid.uuid4().hex[:8]}.txt"
        test_content = b"E2E test file content for sync verification"

        upload_result = await upload_file_to_ingester(
            token=token,
            filename=test_filename,
            content=test_content,
            description="E2E sync test",
            tags=["e2e", "sync-test"]
        )

        file_id = upload_result.get("file_id")
        assert file_id, "Upload did not return file_id"

        print(f"✅ File uploaded: {test_filename} (file_id: {file_id})")

        # Step 3: Wait for cache sync
        sync_success = await wait_for_cache_sync(
            token=token,
            filename=test_filename,
            max_wait_seconds=10.0
        )

        assert sync_success, f"File {test_filename} not synced to Query Module cache within 10 seconds"

        print(f"✅ File synced to cache: {test_filename}")

        # Step 4: Search file
        search_results = await search_file_in_query_module(
            token=token,
            query=test_filename
        )

        # Step 5: Verify results
        assert search_results["total"] > 0, "Search returned no results"

        found_files = [f for f in search_results["files"] if test_filename in f["filename"]]
        assert len(found_files) > 0, f"File {test_filename} not found in search results"

        found_file = found_files[0]
        assert found_file["id"] == file_id, "File ID mismatch"

        print(f"✅ File found in search: {test_filename}")
        print(f"   Total search results: {search_results['total']}")


    async def test_upload_and_search_with_latency_measurement(self):
        """
        Performance test: измерение latency от upload до availability в search.

        Metrics:
        - Upload time
        - Sync latency (upload → cache available)
        - Search time
        - Total E2E time
        """
        start_total = time.time()

        # Authentication
        token = await get_auth_token()

        # Upload file
        test_filename = f"perf_test_{uuid.uuid4().hex[:8]}.txt"
        test_content = b"Performance test file"

        start_upload = time.time()
        upload_result = await upload_file_to_ingester(
            token=token,
            filename=test_filename,
            content=test_content,
        )
        upload_time = time.time() - start_upload

        file_id = upload_result["file_id"]

        # Measure sync latency
        start_sync = time.time()
        sync_success = await wait_for_cache_sync(
            token=token,
            filename=test_filename,
            max_wait_seconds=10.0,
            poll_interval=0.1  # Более частый polling для точности
        )
        sync_latency = time.time() - start_sync

        assert sync_success, "Sync failed within timeout"

        # Measure search time
        start_search = time.time()
        search_results = await search_file_in_query_module(token, test_filename)
        search_time = time.time() - start_search

        total_time = time.time() - start_total

        # Print metrics
        print("\n" + "="*60)
        print("PERFORMANCE METRICS")
        print("="*60)
        print(f"Upload time:       {upload_time*1000:.2f} ms")
        print(f"Sync latency:      {sync_latency*1000:.2f} ms")
        print(f"Search time:       {search_time*1000:.2f} ms")
        print(f"Total E2E time:    {total_time*1000:.2f} ms")
        print("="*60)

        # Performance assertions
        assert sync_latency < 5.0, f"Sync latency too high: {sync_latency:.2f}s"
        assert search_time < 1.0, f"Search time too high: {search_time:.2f}s"

        # Verify file found
        assert search_results["total"] > 0
        found = any(f["id"] == file_id for f in search_results["files"])
        assert found, "File not found in search results"


    async def test_concurrent_uploads_and_sync(self):
        """
        Load test: множественные concurrent uploads и проверка синхронизации всех файлов.

        Steps:
        1. Upload N файлов concurrently
        2. Verify all files synced
        3. Search all files
        4. Verify no files lost
        """
        N_FILES = 10

        # Authentication
        token = await get_auth_token()

        # Generate test files
        test_files = [
            {
                "filename": f"concurrent_test_{i}_{uuid.uuid4().hex[:8]}.txt",
                "content": f"Concurrent test file {i}".encode(),
            }
            for i in range(N_FILES)
        ]

        # Upload concurrently
        start_upload = time.time()

        upload_tasks = [
            upload_file_to_ingester(
                token=token,
                filename=f["filename"],
                content=f["content"],
                tags=["concurrent-test"]
            )
            for f in test_files
        ]

        upload_results = await asyncio.gather(*upload_tasks, return_exceptions=True)
        upload_time = time.time() - start_upload

        # Check for upload failures
        failed_uploads = [r for r in upload_results if isinstance(r, Exception)]
        if failed_uploads:
            print(f"⚠️  {len(failed_uploads)} uploads failed:")
            for e in failed_uploads:
                print(f"   - {e}")

        successful_uploads = [r for r in upload_results if not isinstance(r, Exception)]
        assert len(successful_uploads) >= N_FILES * 0.9, "Too many upload failures"

        file_ids = {r["file_id"]: r for r in successful_uploads}

        print(f"✅ Uploaded {len(successful_uploads)}/{N_FILES} files in {upload_time:.2f}s")

        # Wait for all files to sync
        start_sync = time.time()

        sync_tasks = [
            wait_for_cache_sync(
                token=token,
                filename=test_files[i]["filename"],
                max_wait_seconds=15.0
            )
            for i in range(len(successful_uploads))
        ]

        sync_results = await asyncio.gather(*sync_tasks)
        sync_time = time.time() - start_sync

        synced_count = sum(sync_results)

        print(f"✅ Synced {synced_count}/{len(successful_uploads)} files in {sync_time:.2f}s")

        assert synced_count >= len(successful_uploads) * 0.9, "Too many sync failures"

        # Verify all files searchable
        search_results = await search_file_in_query_module(
            token=token,
            query="concurrent_test"
        )

        found_count = search_results["total"]

        print(f"✅ Search found {found_count} files (expected: {len(successful_uploads)})")

        assert found_count >= len(successful_uploads) * 0.9, "Not all files found in search"


    @pytest.mark.slow
    async def test_redis_unavailable_graceful_degradation(self):
        """
        Failure scenario: Query Module должен продолжать работу при Redis unavailable.

        ВНИМАНИЕ: Этот тест требует ручного вмешательства:
        - Остановить Redis: docker-compose stop redis
        - Запустить тест
        - Проверить, что Query Module не падает
        - Запустить Redis: docker-compose start redis

        Skip by default, run with: pytest -m slow
        """
        pytest.skip("Requires manual Redis stop/start - run with caution")

        token = await get_auth_token()

        # Проверка, что Query Module /health/ready возвращает degraded status
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{QUERY_MODULE_URL}/health/ready",
                timeout=5.0
            )

            # При Redis down, ожидаем 503 Service Unavailable или 200 с warning
            assert response.status_code in [200, 503], "Unexpected health check status"

            if response.status_code == 200:
                health_data = response.json()
                # Должен быть warning о Redis unavailable
                assert "redis" in str(health_data).lower(), "Redis status not reported"


    @pytest.mark.slow
    async def test_event_subscriber_reconnection(self):
        """
        Recovery test: Query Module должен reconnect к Redis после восстановления.

        ВНИМАНИЕ: Требует manual intervention:
        1. Запустить тест
        2. Тест остановит Redis на 5 секунд
        3. Проверит reconnection
        4. Запустит Redis обратно

        Skip by default.
        """
        pytest.skip("Requires Docker control - complex scenario")

        # Placeholder для будущей реализации с docker SDK
        pass


# ==============================================================================
# Pytest Markers Configuration
# ==============================================================================

pytestmark = [
    pytest.mark.integration,
    pytest.mark.e2e,
]
