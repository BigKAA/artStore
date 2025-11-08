"""
Unit tests для file download API endpoint и service.

Тестирует HTTP Range requests (RFC 7233) и streaming download.
"""

import pytest
from fastapi.testclient import TestClient
from pathlib import Path
import tempfile
import shutil
from io import BytesIO
from datetime import datetime, timezone
import hashlib

from app.main import app
from app.services.file_download import FileDownloadService, RangeNotSatisfiableError
from app.core.config import get_config


@pytest.fixture
def test_storage_dir():
    """Create temporary storage directory."""
    temp_dir = Path(tempfile.mkdtemp())
    yield temp_dir
    # Cleanup
    shutil.rmtree(temp_dir)


@pytest.fixture
def download_service(test_storage_dir, monkeypatch):
    """Create download service with test storage directory."""
    config = get_config()
    monkeypatch.setattr(config.storage, "local_base_path", str(test_storage_dir))

    service = FileDownloadService()
    return service


@pytest.fixture
def sample_file(test_storage_dir):
    """Create a sample file for testing."""
    # Create directory structure
    storage_path = test_storage_dir / "2024/01/01/12"
    storage_path.mkdir(parents=True, exist_ok=True)

    # Create test file with known content
    file_path = storage_path / "test_file.txt"
    content = b"0123456789" * 100  # 1000 bytes
    file_path.write_bytes(content)

    return {
        "path": file_path,
        "content": content,
        "size": len(content),
        "storage_path": "2024/01/01/12",
        "storage_filename": "test_file.txt"
    }


class TestFileDownloadService:
    """Тесты для FileDownloadService business logic."""

    def test_get_file_path_success(self, download_service, sample_file):
        """Тест успешного получения file path."""
        file_path = download_service.get_file_path(
            storage_path=sample_file["storage_path"],
            storage_filename=sample_file["storage_filename"]
        )

        assert file_path.exists()
        assert file_path == sample_file["path"]

    def test_get_file_path_traversal_protection(self, download_service):
        """Тест защиты от path traversal атак."""
        with pytest.raises(ValueError, match="Path traversal"):
            download_service.get_file_path(
                storage_path="../../../etc",
                storage_filename="passwd"
            )

        with pytest.raises(ValueError, match="Path traversal"):
            download_service.get_file_path(
                storage_path="2024/01/01",
                storage_filename="../../../../../../etc/passwd"
            )

    def test_generate_etag(self, download_service, sample_file):
        """Тест генерации ETag."""
        file_path = sample_file["path"]
        file_size = sample_file["size"]
        modified_time = datetime.fromtimestamp(
            file_path.stat().st_mtime,
            tz=timezone.utc
        )

        etag = download_service.generate_etag(
            file_path=file_path,
            file_size=file_size,
            modified_time=modified_time
        )

        # ETag должен быть в кавычках
        assert etag.startswith('"')
        assert etag.endswith('"')

        # ETag должен быть детерминированным
        etag2 = download_service.generate_etag(
            file_path=file_path,
            file_size=file_size,
            modified_time=modified_time
        )
        assert etag == etag2

    def test_parse_range_single(self, download_service):
        """Тест парсинга single range."""
        ranges = download_service.parse_range_header("bytes=0-99", 1000)

        assert len(ranges) == 1
        assert ranges[0] == (0, 99)

    def test_parse_range_multiple(self, download_service):
        """Тест парсинга multiple ranges."""
        ranges = download_service.parse_range_header("bytes=0-99,200-299", 1000)

        assert len(ranges) == 2
        assert ranges[0] == (0, 99)
        assert ranges[1] == (200, 299)

    def test_parse_range_suffix(self, download_service):
        """Тест парсинга suffix range (последние N байт)."""
        ranges = download_service.parse_range_header("bytes=-100", 1000)

        assert len(ranges) == 1
        assert ranges[0] == (900, 999)

    def test_parse_range_open_end(self, download_service):
        """Тест парсинга open-ended range."""
        ranges = download_service.parse_range_header("bytes=500-", 1000)

        assert len(ranges) == 1
        assert ranges[0] == (500, 999)

    def test_parse_range_exceeds_file_size(self, download_service):
        """Тест range превышающего размер файла."""
        ranges = download_service.parse_range_header("bytes=0-2000", 1000)

        # End должен быть clamped к file_size - 1
        assert len(ranges) == 1
        assert ranges[0] == (0, 999)

    def test_parse_range_invalid_format(self, download_service):
        """Тест невалидного формата range."""
        with pytest.raises(RangeNotSatisfiableError):
            download_service.parse_range_header("invalid", 1000)

        with pytest.raises(RangeNotSatisfiableError):
            download_service.parse_range_header("bytes=abc-def", 1000)

    def test_parse_range_start_greater_than_end(self, download_service):
        """Тест range где start > end."""
        with pytest.raises(RangeNotSatisfiableError):
            download_service.parse_range_header("bytes=500-100", 1000)

    def test_parse_range_start_exceeds_file_size(self, download_service):
        """Тест range где start >= file_size."""
        with pytest.raises(RangeNotSatisfiableError):
            download_service.parse_range_header("bytes=1000-1500", 1000)

    def test_stream_file_full(self, download_service, sample_file):
        """Тест streaming полного файла."""
        content_parts = []

        for chunk in download_service.stream_file(sample_file["path"]):
            content_parts.append(chunk)

        full_content = b"".join(content_parts)
        assert full_content == sample_file["content"]

    def test_stream_file_range(self, download_service, sample_file):
        """Тест streaming части файла."""
        # First 100 bytes
        content_parts = []

        for chunk in download_service.stream_file(
            sample_file["path"],
            start=0,
            end=99
        ):
            content_parts.append(chunk)

        range_content = b"".join(content_parts)
        assert range_content == sample_file["content"][0:100]
        assert len(range_content) == 100

    def test_stream_file_middle_range(self, download_service, sample_file):
        """Тест streaming middle range."""
        # Bytes 100-199
        content_parts = []

        for chunk in download_service.stream_file(
            sample_file["path"],
            start=100,
            end=199
        ):
            content_parts.append(chunk)

        range_content = b"".join(content_parts)
        assert range_content == sample_file["content"][100:200]

    def test_stream_file_last_byte(self, download_service, sample_file):
        """Тест streaming последнего байта."""
        content_parts = []

        for chunk in download_service.stream_file(
            sample_file["path"],
            start=999,
            end=999
        ):
            content_parts.append(chunk)

        range_content = b"".join(content_parts)
        assert range_content == sample_file["content"][999:1000]
        assert len(range_content) == 1

    def test_stream_multipart_ranges(self, download_service, sample_file):
        """Тест streaming multiple ranges в multipart format."""
        ranges = [(0, 99), (200, 299)]

        content_parts = []
        for chunk in download_service.stream_multipart_ranges(
            file_path=sample_file["path"],
            ranges=ranges,
            content_type="text/plain"
        ):
            content_parts.append(chunk)

        multipart_content = b"".join(content_parts)

        # Check multipart format
        assert b"--RANGE_SEPARATOR" in multipart_content
        assert b"Content-Type: text/plain" in multipart_content
        assert b"Content-Range: bytes 0-99/1000" in multipart_content
        assert b"Content-Range: bytes 200-299/1000" in multipart_content

        # Check actual data is present
        assert sample_file["content"][0:100] in multipart_content
        assert sample_file["content"][200:300] in multipart_content


class TestFileDownloadAPI:
    """Тесты для file download API endpoint (требуют PostgreSQL + реальный upload)."""

    @pytest.mark.skip(reason="Requires full upload flow with PostgreSQL")
    def test_download_full_file(self):
        """Тест загрузки полного файла."""
        # This would require full upload → download flow
        pass

    @pytest.mark.skip(reason="Requires full upload flow with PostgreSQL")
    def test_download_with_range(self):
        """Тест загрузки с Range header."""
        pass

    @pytest.mark.skip(reason="Requires full upload flow with PostgreSQL")
    def test_download_with_etag_validation(self):
        """Тест conditional request с ETag."""
        pass

    @pytest.mark.skip(reason="Requires full upload flow with PostgreSQL")
    def test_download_invalid_file_id(self):
        """Тест загрузки несуществующего файла."""
        pass


# Integration test fixtures (для будущего использования с PostgreSQL)
class TestFileDownloadIntegration:
    """
    Integration tests для полного upload-download цикла.

    Требуют:
    - PostgreSQL database
    - Real file upload
    - Full API testing
    """

    @pytest.mark.skip(reason="Requires PostgreSQL and full stack")
    def test_upload_then_download(self):
        """Тест полного цикла: upload → download."""
        pass

    @pytest.mark.skip(reason="Requires PostgreSQL and full stack")
    def test_resumable_download(self):
        """Тест resumable download через multiple range requests."""
        pass

    @pytest.mark.skip(reason="Requires PostgreSQL and full stack")
    def test_concurrent_downloads(self):
        """Тест одновременных загрузок одного файла."""
        pass

    @pytest.mark.skip(reason="Requires PostgreSQL and full stack")
    def test_download_large_file_performance(self):
        """Тест performance на больших файлах (>100MB)."""
        pass
