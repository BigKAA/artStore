"""
Unit tests для Pydantic schemas (search, download).

Тестирует:
- Валидацию входных данных
- Сериализацию/десериализацию
- Custom validators
- Computed properties
"""

import pytest
from datetime import datetime, timezone
from pydantic import ValidationError

from app.schemas.search import (
    SearchRequest,
    SearchResponse,
    FileMetadataResponse,
    SearchMode,
    SortField,
    SortOrder
)
from app.schemas.download import (
    DownloadMetadata,
    RangeRequest,
    DownloadProgress,
    DownloadResponse
)


# ========================================
# SearchRequest Tests
# ========================================

@pytest.mark.unit
class TestSearchRequest:
    """Tests для SearchRequest schema."""

    def test_valid_search_request(self):
        """Тест валидного search request."""
        request = SearchRequest(
            query="test document",
            mode=SearchMode.PARTIAL,
            limit=50,
            offset=0
        )
        
        assert request.query == "test document"
        assert request.mode == SearchMode.PARTIAL
        assert request.limit == 50
        assert request.offset == 0

    def test_default_values(self):
        """Тест значений по умолчанию."""
        request = SearchRequest()
        
        assert request.mode == SearchMode.PARTIAL
        assert request.limit == 100
        assert request.offset == 0
        assert request.sort_by == SortField.CREATED_AT
        assert request.sort_order == SortOrder.DESC

    def test_query_length_validation(self):
        """Тест валидации длины query."""
        # Слишком длинный query
        with pytest.raises(ValidationError) as exc_info:
            SearchRequest(query="a" * 501)

        assert "string_too_long" in str(exc_info.value)

    def test_tags_validation(self):
        """Тест валидации тегов."""
        # Слишком много тегов
        with pytest.raises(ValidationError) as exc_info:
            SearchRequest(tags=["tag"] * 51)
        
        assert "Maximum 50 tags" in str(exc_info.value)
        
        # Слишком длинный тег
        with pytest.raises(ValidationError) as exc_info:
            SearchRequest(tags=["a" * 51])
        
        assert "Tag length must not exceed" in str(exc_info.value)

    def test_file_size_validation(self):
        """Тест валидации размера файла."""
        # Отрицательный размер
        with pytest.raises(ValidationError) as exc_info:
            SearchRequest(min_size=-1)

        assert "greater_than_equal" in str(exc_info.value)

    def test_limit_validation(self):
        """Тест валидации limit."""
        # Превышение максимума
        with pytest.raises(ValidationError) as exc_info:
            SearchRequest(limit=1001)
        
        assert "less than or equal to 1000" in str(exc_info.value)
        
        # Меньше минимума
        with pytest.raises(ValidationError) as exc_info:
            SearchRequest(limit=0)
        
        assert "greater than or equal to 1" in str(exc_info.value)

    def test_has_search_criteria(self):
        """Тест метода has_search_criteria()."""
        # С критериями
        request = SearchRequest(query="test")
        assert request.has_search_criteria() is True
        
        request = SearchRequest(filename="document.pdf")
        assert request.has_search_criteria() is True
        
        request = SearchRequest(tags=["test"])
        assert request.has_search_criteria() is True
        
        # Без критериев
        request = SearchRequest()
        assert request.has_search_criteria() is False


# ========================================
# SearchResponse Tests
# ========================================

@pytest.mark.unit
class TestSearchResponse:
    """Tests для SearchResponse schema."""

    def test_valid_search_response(self, sample_file_metadata):
        """Тест валидного search response."""
        file_response = FileMetadataResponse(**sample_file_metadata)
        
        response = SearchResponse(
            results=[file_response],
            total_count=1,
            limit=100,
            offset=0,
            has_more=False
        )
        
        assert len(response.results) == 1
        assert response.total_count == 1
        assert response.has_more is False

    def test_current_page_property(self):
        """Тест computed property current_page."""
        response = SearchResponse(
            results=[],
            total_count=100,
            limit=10,
            offset=20,
            has_more=True
        )
        
        assert response.current_page == 3  # (20 // 10) + 1

    def test_total_pages_property(self):
        """Тест computed property total_pages."""
        response = SearchResponse(
            results=[],
            total_count=95,
            limit=10,
            offset=0,
            has_more=True
        )
        
        assert response.total_pages == 10  # ceiling(95 / 10)
        
        # Пустой результат
        response = SearchResponse(
            results=[],
            total_count=0,
            limit=10,
            offset=0,
            has_more=False
        )
        
        assert response.total_pages == 0


# ========================================
# DownloadMetadata Tests
# ========================================

@pytest.mark.unit
class TestDownloadMetadata:
    """Tests для DownloadMetadata schema."""

    def test_valid_download_metadata(self):
        """Тест валидного download metadata."""
        from datetime import datetime, timezone

        metadata = DownloadMetadata(
            id="550e8400-e29b-41d4-a716-446655440000",
            filename="document.pdf",
            file_size=1024000,
            sha256_hash="a" * 64,
            storage_element_url="http://storage:8010",
            supports_range_requests=True,
            storage_element_id="storage-01",
            created_at=datetime.now(timezone.utc)
        )

        assert metadata.filename == "document.pdf"
        assert metadata.file_size == 1024000
        assert metadata.supports_range_requests is True

    def test_default_supports_range(self):
        """Тест значения по умолчанию для supports_range_requests."""
        from datetime import datetime, timezone

        metadata = DownloadMetadata(
            id="test-id",
            filename="test.pdf",
            file_size=1000,
            sha256_hash="a" * 64,
            storage_element_url="http://storage:8010",
            storage_element_id="storage-01",
            created_at=datetime.now(timezone.utc)
        )

        assert metadata.supports_range_requests is True


# ========================================
# RangeRequest Tests
# ========================================

@pytest.mark.unit
class TestRangeRequest:
    """Tests для RangeRequest schema."""

    def test_range_request_with_end(self):
        """Тест Range request с указанным end."""
        range_req = RangeRequest(start=0, end=1023)
        
        assert range_req.to_header_value() == "bytes=0-1023"

    def test_range_request_without_end(self):
        """Тест Range request без end (до конца файла)."""
        range_req = RangeRequest(start=1024, end=None)
        
        assert range_req.to_header_value() == "bytes=1024-"

    def test_negative_start_validation(self):
        """Тест валидации отрицательного start."""
        with pytest.raises(ValidationError):
            RangeRequest(start=-1)


# ========================================
# DownloadProgress Tests
# ========================================

@pytest.mark.unit
class TestDownloadProgress:
    """Tests для DownloadProgress schema."""

    def test_progress_percent_calculation(self):
        """Тест вычисления процента прогресса."""
        progress = DownloadProgress(
            file_id="test-id",
            total_size=1000,
            downloaded_size=500
        )
        
        assert progress.progress_percent == 50.0
        
        # Полная загрузка
        progress = DownloadProgress(
            file_id="test-id",
            total_size=1000,
            downloaded_size=1000
        )
        
        assert progress.progress_percent == 100.0

    def test_progress_percent_zero_total(self):
        """Тест процента при total_size = 0."""
        progress = DownloadProgress(
            file_id="test-id",
            total_size=0,
            downloaded_size=0
        )
        
        assert progress.progress_percent == 0.0

    def test_is_complete(self):
        """Тест проверки завершенности загрузки."""
        # Не завершена
        progress = DownloadProgress(
            file_id="test-id",
            total_size=1000,
            downloaded_size=500
        )
        
        assert progress.is_complete is False
        
        # Завершена
        progress = DownloadProgress(
            file_id="test-id",
            total_size=1000,
            downloaded_size=1000
        )
        
        assert progress.is_complete is True
        
        # Превышен размер (edge case)
        progress = DownloadProgress(
            file_id="test-id",
            total_size=1000,
            downloaded_size=1500
        )
        
        assert progress.is_complete is True

    def test_resume_from_calculation(self):
        """Тест вычисления resume_from."""
        # Есть откуда продолжать
        progress = DownloadProgress(
            file_id="test-id",
            total_size=1000,
            downloaded_size=500,
            resume_from=500
        )
        
        assert progress.resume_from == 500
        
        # Загрузка завершена
        progress = DownloadProgress(
            file_id="test-id",
            total_size=1000,
            downloaded_size=1000,
            resume_from=None
        )
        
        assert progress.resume_from is None


# ========================================
# DownloadResponse Tests
# ========================================

@pytest.mark.unit
class TestDownloadResponse:
    """Tests для DownloadResponse schema."""

    def test_valid_download_response(self):
        """Тест валидного download response."""
        response = DownloadResponse(
            file_id="test-id",
            filename="document.pdf",
            content_type="application/pdf",
            content_length=1024000,
            sha256_hash="a" * 64
        )
        
        assert response.filename == "document.pdf"
        assert response.content_type == "application/pdf"
        assert response.supports_resume is True
        assert response.accept_ranges == "bytes"

    def test_default_values(self):
        """Тест значений по умолчанию."""
        response = DownloadResponse(
            file_id="test-id",
            filename="test.pdf",
            content_type="application/pdf",
            content_length=1000,
            sha256_hash="a" * 64
        )
        
        assert response.supports_resume is True
        assert response.accept_ranges == "bytes"
