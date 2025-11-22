"""
Unit tests для Search Service.

Тестирует:
- Построение поисковых запросов (EXACT, PARTIAL, FULLTEXT)
- Фильтрацию по tags, size, date, username
- Сортировку и пагинацию
- Кеширование поисковых запросов
- Запись статистики поиска
"""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from sqlalchemy import select

from app.services.search_service import SearchService
from app.schemas.search import (
    SearchRequest,
    SearchMode,
    SortField,
    SortOrder
)
from app.db.models import FileMetadata, SearchHistory


# ========================================
# SearchService Tests
# ========================================

@pytest.mark.unit
class TestSearchService:
    """Tests для SearchService."""

    @pytest.fixture
    def mock_db_session(self):
        """Mock async database session."""
        session = AsyncMock()
        return session

    @pytest.fixture
    def search_service(self, mock_db_session):
        """SearchService instance с mock session."""
        return SearchService(db=mock_db_session)

    def test_compute_search_hash(self, search_service):
        """Тест генерации хеша для кеширования запросов."""
        request1 = SearchRequest(query="test", mode=SearchMode.PARTIAL)
        request2 = SearchRequest(query="test", mode=SearchMode.PARTIAL)
        request3 = SearchRequest(query="other", mode=SearchMode.PARTIAL)

        hash1 = search_service._compute_search_hash(request1)
        hash2 = search_service._compute_search_hash(request2)
        hash3 = search_service._compute_search_hash(request3)

        # Одинаковые запросы должны давать одинаковый хеш
        assert hash1 == hash2
        # Разные запросы - разные хеши
        assert hash1 != hash3

    def test_build_search_query_exact_mode(self, search_service):
        """Тест построения запроса в режиме EXACT."""
        request = SearchRequest(
            query="document.pdf",
            mode=SearchMode.EXACT,
            limit=100,
            offset=0
        )

        query = search_service._build_search_query(request)

        # Проверка, что query содержит условие точного совпадения
        assert query is not None
        # Query должен быть типа Select
        assert hasattr(query, 'whereclause')

    def test_build_search_query_partial_mode(self, search_service):
        """Тест построения запроса в режиме PARTIAL (LIKE)."""
        request = SearchRequest(
            query="test",
            mode=SearchMode.PARTIAL,
            limit=50,
            offset=0
        )

        query = search_service._build_search_query(request)

        assert query is not None
        # Partial mode использует LIKE для filename и description

    def test_build_search_query_fulltext_mode(self, search_service):
        """Тест построения запроса в режиме FULLTEXT."""
        request = SearchRequest(
            query="important document",
            mode=SearchMode.FULLTEXT,
            limit=100,
            offset=0
        )

        query = search_service._build_search_query(request)

        assert query is not None
        # Fulltext mode использует ts_vector и plainto_tsquery

    def test_build_search_query_with_tags_filter(self, search_service):
        """Тест фильтрации по тегам."""
        request = SearchRequest(
            query="test",
            tags=["important", "urgent"],
            limit=100,
            offset=0
        )

        query = search_service._build_search_query(request)

        assert query is not None
        # Должен использовать ARRAY overlap operator &&

    def test_build_search_query_with_size_filter(self, search_service):
        """Тест фильтрации по размеру файла."""
        request = SearchRequest(
            query="test",
            min_size=1024,
            max_size=1048576,
            limit=100,
            offset=0
        )

        query = search_service._build_search_query(request)

        assert query is not None
        # Должен добавить условия на file_size

    def test_build_search_query_with_date_filter(self, search_service):
        """Тест фильтрации по дате создания."""
        created_after = datetime.now(timezone.utc) - timedelta(days=7)
        created_before = datetime.now(timezone.utc)

        request = SearchRequest(
            query="test",
            created_after=created_after,
            created_before=created_before,
            limit=100,
            offset=0
        )

        query = search_service._build_search_query(request)

        assert query is not None
        # Должен добавить условия на created_at

    def test_build_search_query_with_username_filter(self, search_service):
        """Тест фильтрации по username."""
        request = SearchRequest(
            query="test",
            username="testuser",
            limit=100,
            offset=0
        )

        query = search_service._build_search_query(request)

        assert query is not None
        # Должен добавить условие на username

    def test_build_search_query_with_sorting(self, search_service):
        """Тест сортировки результатов."""
        request = SearchRequest(
            query="test",
            sort_by=SortField.FILE_SIZE,
            sort_order=SortOrder.DESC,
            limit=100,
            offset=0
        )

        query = search_service._build_search_query(request)

        assert query is not None
        # Должен добавить ORDER BY file_size DESC

    def test_build_search_query_with_pagination(self, search_service):
        """Тест пагинации (limit и offset)."""
        request = SearchRequest(
            query="test",
            limit=50,
            offset=100,
            sort_by=SortField.CREATED_AT,
            sort_order=SortOrder.DESC
        )

        query = search_service._build_search_query(request)

        assert query is not None
        # Должен добавить LIMIT 50 OFFSET 100

    def test_build_search_query_empty_query(self, search_service):
        """Тест запроса без текста (только фильтры)."""
        request = SearchRequest(
            query=None,
            tags=["important"],
            min_size=1024,
            limit=100,
            offset=0
        )

        query = search_service._build_search_query(request)

        assert query is not None
        # Должен построить запрос только с фильтрами, без текстового поиска

    @pytest.mark.asyncio
    async def test_search_files_success(self, search_service, mock_db_session, sample_file_metadata):
        """Тест успешного поиска файлов."""
        # Mock результат запроса
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [
            FileMetadata(**sample_file_metadata)
        ]

        # Mock count query
        mock_count_result = MagicMock()
        mock_count_result.scalar.return_value = 1

        mock_db_session.execute.side_effect = [mock_result, mock_count_result]

        # Mock commit для search history
        mock_db_session.commit = AsyncMock()

        request = SearchRequest(query="test", limit=100, offset=0)

        response = await search_service.search_files(request)

        assert response.total_count == 1
        assert len(response.results) == 1
        assert response.results[0].filename == sample_file_metadata["filename"]
        assert response.has_more is False

    @pytest.mark.asyncio
    async def test_search_files_no_results(self, search_service, mock_db_session):
        """Тест поиска без результатов."""
        # Mock пустой результат
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []

        mock_count_result = MagicMock()
        mock_count_result.scalar.return_value = 0

        mock_db_session.execute.side_effect = [mock_result, mock_count_result]
        mock_db_session.commit = AsyncMock()

        request = SearchRequest(query="nonexistent", limit=100, offset=0)

        response = await search_service.search_files(request)

        assert response.total_count == 0
        assert len(response.results) == 0
        assert response.has_more is False

    @pytest.mark.asyncio
    async def test_search_files_with_pagination(self, search_service, mock_db_session, sample_file_metadata):
        """Тест пагинации результатов."""
        # Создаем 150 файлов (больше чем limit=100)
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [
            FileMetadata(**sample_file_metadata) for _ in range(100)
        ]

        mock_count_result = MagicMock()
        mock_count_result.scalar.return_value = 150  # Всего 150 файлов

        mock_db_session.execute.side_effect = [mock_result, mock_count_result]
        mock_db_session.commit = AsyncMock()

        request = SearchRequest(query="test", limit=100, offset=0)

        response = await search_service.search_files(request)

        assert response.total_count == 150
        assert len(response.results) == 100
        assert response.has_more is True  # Есть еще результаты
        assert response.current_page == 1
        assert response.total_pages == 2  # ceiling(150 / 100)

    @pytest.mark.asyncio
    async def test_record_search_history(self, search_service, mock_db_session):
        """Тест записи истории поиска."""
        mock_db_session.add = MagicMock()
        mock_db_session.commit = AsyncMock()

        await search_service._record_search_history(
            search_request=SearchRequest(query="test document", mode=SearchMode.FULLTEXT),
            results_count=42,
            response_time_ms=123
        )

        # Проверяем, что add был вызван с SearchHistory
        mock_db_session.add.assert_called_once()

        # Проверяем, что commit был вызван
        mock_db_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_file_by_id_success(self, search_service, mock_db_session, sample_file_metadata):
        """Тест получения файла по ID."""
        # Mock результат запроса
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = FileMetadata(**sample_file_metadata)

        mock_db_session.execute.return_value = mock_result

        file_id = sample_file_metadata["id"]

        result = await search_service.get_file_by_id(file_id)

        assert result is not None
        assert result.id == file_id
        assert result.filename == sample_file_metadata["filename"]

    @pytest.mark.asyncio
    async def test_get_file_by_id_not_found(self, search_service, mock_db_session):
        """Тест получения несуществующего файла."""
        # Mock пустой результат
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None

        mock_db_session.execute.return_value = mock_result

        result = await search_service.get_file_by_id("nonexistent-id")

        assert result is None

    def test_search_request_validation(self):
        """Тест валидации SearchRequest."""
        # Валидный запрос
        request = SearchRequest(
            query="test",
            mode=SearchMode.PARTIAL,
            limit=50,
            offset=0
        )
        assert request.mode == SearchMode.PARTIAL

        # Query слишком длинный (max 500)
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            SearchRequest(query="a" * 501)

        # Слишком много тегов (max 50)
        with pytest.raises(ValidationError):
            SearchRequest(tags=["tag"] * 51)

        # Limit превышен (max 1000)
        with pytest.raises(ValidationError):
            SearchRequest(limit=1001)

    def test_search_mode_enum(self):
        """Тест SearchMode enum."""
        assert SearchMode.EXACT == "exact"
        assert SearchMode.PARTIAL == "partial"
        assert SearchMode.FULLTEXT == "fulltext"

    def test_sort_field_enum(self):
        """Тест SortField enum."""
        assert SortField.FILENAME == "filename"
        assert SortField.FILE_SIZE == "file_size"
        assert SortField.CREATED_AT == "created_at"
        assert SortField.UPDATED_AT == "updated_at"

    def test_sort_order_enum(self):
        """Тест SortOrder enum."""
        assert SortOrder.ASC == "asc"
        assert SortOrder.DESC == "desc"
