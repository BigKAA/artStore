"""
Integration tests для Search API endpoints.

Тестирует:
- POST /api/search - Поиск файлов с различными режимами
- GET /api/search/{file_id} - Получение метаданных файла
- JWT authentication integration
- Multi-level caching behavior
- Error handling
"""

import pytest
from datetime import datetime, timezone
from fastapi import status
from httpx import AsyncClient

from app.main import app
from app.db.models import FileMetadata
from app.core.security import UserContext, UserRole, TokenType


# ========================================
# Search API Integration Tests
# ========================================

@pytest.mark.integration
@pytest.mark.asyncio
class TestSearchAPIIntegration:
    """Integration tests для Search API."""

    async def test_search_files_fulltext_success(
        self,
        async_session,
        valid_jwt_token,
        sample_file_metadata
    ):
        """Тест успешного full-text поиска файлов."""
        # Подготовка тестовых данных
        file_meta = FileMetadata(**sample_file_metadata)
        async_session.add(file_meta)
        await async_session.commit()

        # HTTP request
        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.post(
                "/api/search",
                json={
                    "query": "test document",
                    "mode": "fulltext",
                    "limit": 100,
                    "offset": 0
                },
                headers={"Authorization": f"Bearer {valid_jwt_token}"}
            )

        # Assertions
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "results" in data
        assert "total_count" in data
        assert data["total_count"] >= 0
        assert isinstance(data["results"], list)

    async def test_search_files_partial_match(
        self,
        async_session,
        valid_jwt_token,
        sample_file_metadata
    ):
        """Тест partial match поиска."""
        # Подготовка данных
        file_meta = FileMetadata(**sample_file_metadata)
        async_session.add(file_meta)
        await async_session.commit()

        # HTTP request с partial mode
        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.post(
                "/api/search",
                json={
                    "query": "doc",
                    "mode": "partial",
                    "limit": 50
                },
                headers={"Authorization": f"Bearer {valid_jwt_token}"}
            )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["total_count"] >= 0

    async def test_search_files_exact_match(
        self,
        async_session,
        valid_jwt_token,
        sample_file_metadata
    ):
        """Тест exact match поиска."""
        file_meta = FileMetadata(**sample_file_metadata)
        async_session.add(file_meta)
        await async_session.commit()

        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.post(
                "/api/search",
                json={
                    "query": "test-document.pdf",
                    "mode": "exact",
                    "limit": 10
                },
                headers={"Authorization": f"Bearer {valid_jwt_token}"}
            )

        assert response.status_code == status.HTTP_200_OK

    async def test_search_files_with_tags_filter(
        self,
        async_session,
        valid_jwt_token,
        sample_file_metadata
    ):
        """Тест поиска с фильтрацией по тегам."""
        file_meta = FileMetadata(**sample_file_metadata)
        async_session.add(file_meta)
        await async_session.commit()

        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.post(
                "/api/search",
                json={
                    "query": "test",
                    "mode": "partial",
                    "tags": ["test", "document"],
                    "limit": 100
                },
                headers={"Authorization": f"Bearer {valid_jwt_token}"}
            )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        # Проверяем что результаты содержат указанные теги
        for result in data["results"]:
            assert any(tag in result.get("tags", []) for tag in ["test", "document"])

    async def test_search_files_with_pagination(
        self,
        async_session,
        valid_jwt_token,
        sample_file_metadata
    ):
        """Тест пагинации результатов поиска."""
        # Создаем несколько файлов
        for i in range(5):
            file_meta = FileMetadata(
                **{**sample_file_metadata, "id": f"test-id-{i}", "filename": f"test-{i}.pdf"}
            )
            async_session.add(file_meta)
        await async_session.commit()

        async with AsyncClient(app=app, base_url="http://test") as client:
            # Первая страница
            response1 = await client.post(
                "/api/search",
                json={
                    "query": "test",
                    "mode": "partial",
                    "limit": 2,
                    "offset": 0
                },
                headers={"Authorization": f"Bearer {valid_jwt_token}"}
            )

            # Вторая страница
            response2 = await client.post(
                "/api/search",
                json={
                    "query": "test",
                    "mode": "partial",
                    "limit": 2,
                    "offset": 2
                },
                headers={"Authorization": f"Bearer {valid_jwt_token}"}
            )

        assert response1.status_code == status.HTTP_200_OK
        assert response2.status_code == status.HTTP_200_OK

        data1 = response1.json()
        data2 = response2.json()

        assert len(data1["results"]) <= 2
        assert len(data2["results"]) <= 2

    async def test_search_files_no_criteria_error(
        self,
        valid_jwt_token
    ):
        """Тест ошибки при отсутствии критериев поиска."""
        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.post(
                "/api/search",
                json={
                    "limit": 100,
                    "offset": 0
                },
                headers={"Authorization": f"Bearer {valid_jwt_token}"}
            )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "search criteria" in response.json()["detail"].lower()

    async def test_search_files_unauthorized(self):
        """Тест ошибки авторизации."""
        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.post(
                "/api/search",
                json={
                    "query": "test",
                    "mode": "partial"
                }
                # No Authorization header
            )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    async def test_get_file_metadata_success(
        self,
        async_session,
        valid_jwt_token,
        sample_file_metadata
    ):
        """Тест успешного получения метаданных файла."""
        file_meta = FileMetadata(**sample_file_metadata)
        async_session.add(file_meta)
        await async_session.commit()

        file_id = sample_file_metadata["id"]

        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.get(
                f"/api/search/{file_id}",
                headers={"Authorization": f"Bearer {valid_jwt_token}"}
            )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["id"] == file_id
        assert data["filename"] == sample_file_metadata["filename"]
        assert data["file_size"] == sample_file_metadata["file_size"]

    async def test_get_file_metadata_not_found(
        self,
        valid_jwt_token
    ):
        """Тест ошибки 404 для несуществующего файла."""
        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.get(
                "/api/search/nonexistent-id",
                headers={"Authorization": f"Bearer {valid_jwt_token}"}
            )

        assert response.status_code == status.HTTP_404_NOT_FOUND

    async def test_get_file_metadata_unauthorized(
        self,
        async_session,
        sample_file_metadata
    ):
        """Тест ошибки авторизации при получении метаданных."""
        file_meta = FileMetadata(**sample_file_metadata)
        async_session.add(file_meta)
        await async_session.commit()

        file_id = sample_file_metadata["id"]

        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.get(f"/api/search/{file_id}")

        assert response.status_code == status.HTTP_401_UNAUTHORIZED


# ========================================
# Caching Integration Tests
# ========================================

@pytest.mark.integration
@pytest.mark.asyncio
class TestSearchCachingIntegration:
    """Integration tests для multi-level caching."""

    async def test_cache_hit_on_repeated_metadata_request(
        self,
        async_session,
        valid_jwt_token,
        sample_file_metadata
    ):
        """Тест кеширования метаданных при повторных запросах."""
        file_meta = FileMetadata(**sample_file_metadata)
        async_session.add(file_meta)
        await async_session.commit()

        file_id = sample_file_metadata["id"]

        async with AsyncClient(app=app, base_url="http://test") as client:
            # Первый запрос - cache miss
            response1 = await client.get(
                f"/api/search/{file_id}",
                headers={"Authorization": f"Bearer {valid_jwt_token}"}
            )

            # Второй запрос - cache hit
            response2 = await client.get(
                f"/api/search/{file_id}",
                headers={"Authorization": f"Bearer {valid_jwt_token}"}
            )

        assert response1.status_code == status.HTTP_200_OK
        assert response2.status_code == status.HTTP_200_OK

        # Данные должны быть идентичны
        assert response1.json() == response2.json()
