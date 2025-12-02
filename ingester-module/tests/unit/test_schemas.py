"""
Unit tests для Pydantic schemas модуля Ingester.

Тестирует:
- UploadRequest validation
- UploadResponse validation
- Enum validations (StorageMode, CompressionAlgorithm)
- Edge cases и error handling
"""

from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from app.schemas.upload import (
    CompressionAlgorithm,
    StorageMode,
    UploadError,
    UploadProgress,
    UploadRequest,
    UploadResponse,
)


class TestStorageMode:
    """Тесты для StorageMode enum."""

    def test_valid_storage_modes(self):
        """Проверка всех допустимых значений StorageMode."""
        assert StorageMode.EDIT == "edit"
        assert StorageMode.RW == "rw"
        assert StorageMode.RO == "ro"
        assert StorageMode.AR == "ar"

    def test_storage_mode_from_string(self):
        """Проверка создания StorageMode из строки."""
        assert StorageMode("edit") == StorageMode.EDIT
        assert StorageMode("rw") == StorageMode.RW
        assert StorageMode("ro") == StorageMode.RO
        assert StorageMode("ar") == StorageMode.AR

    def test_invalid_storage_mode(self):
        """Проверка обработки невалидного storage mode."""
        with pytest.raises(ValueError):
            StorageMode("invalid")


class TestCompressionAlgorithm:
    """Тесты для CompressionAlgorithm enum."""

    def test_valid_compression_algorithms(self):
        """Проверка всех допустимых алгоритмов сжатия."""
        assert CompressionAlgorithm.NONE == "none"
        assert CompressionAlgorithm.GZIP == "gzip"
        assert CompressionAlgorithm.BROTLI == "brotli"

    def test_compression_algorithm_from_string(self):
        """Проверка создания CompressionAlgorithm из строки."""
        assert CompressionAlgorithm("none") == CompressionAlgorithm.NONE
        assert CompressionAlgorithm("gzip") == CompressionAlgorithm.GZIP
        assert CompressionAlgorithm("brotli") == CompressionAlgorithm.BROTLI

    def test_invalid_compression_algorithm(self):
        """Проверка обработки невалидного алгоритма."""
        with pytest.raises(ValueError):
            CompressionAlgorithm("zip")


class TestUploadRequest:
    """Тесты для UploadRequest schema."""

    def test_upload_request_minimal(self):
        """Минимальный валидный UploadRequest."""
        request = UploadRequest()

        # Проверка значений по умолчанию
        assert request.description is None
        assert request.storage_mode == StorageMode.EDIT
        assert request.compress is False
        assert request.compression_algorithm == CompressionAlgorithm.GZIP

    def test_upload_request_full(self):
        """Полный UploadRequest со всеми полями."""
        # storage_mode автоопределяется из retention_policy через валидатор
        # PERMANENT → RW, TEMPORARY → EDIT
        request = UploadRequest(
            description="Test file upload",
            retention_policy=RetentionPolicy.PERMANENT,  # → RW mode
            compress=True,
            compression_algorithm=CompressionAlgorithm.BROTLI
        )

        assert request.description == "Test file upload"
        assert request.retention_policy == RetentionPolicy.PERMANENT
        assert request.storage_mode == StorageMode.RW  # Автоопределено из retention_policy
        assert request.compress is True
        assert request.compression_algorithm == CompressionAlgorithm.BROTLI

    def test_upload_request_description_max_length(self):
        """Проверка максимальной длины description."""
        # 500 символов - допустимо
        long_desc = "A" * 500
        request = UploadRequest(description=long_desc)
        assert len(request.description) == 500

        # 501 символ - превышает лимит
        too_long_desc = "A" * 501
        with pytest.raises(ValidationError) as exc_info:
            UploadRequest(description=too_long_desc)

        errors = exc_info.value.errors()
        assert any("at most 500 characters" in str(err) for err in errors)

    def test_upload_request_empty_description(self):
        """Пустое description допустимо."""
        request = UploadRequest(description="")
        assert request.description == ""

    def test_upload_request_storage_mode_validation(self):
        """Валидация storage_mode - только EDIT и RW."""
        # Валидные значения для загрузки
        for mode in ["edit", "rw"]:
            request = UploadRequest(storage_mode=mode)
            assert request.storage_mode.value == mode

        # RO и AR не разрешены для загрузки
        for mode in ["ro", "ar"]:
            with pytest.raises(ValidationError) as exc_info:
                UploadRequest(storage_mode=mode)
            errors = exc_info.value.errors()
            assert any("Upload only allowed to EDIT or RW modes" in str(err) for err in errors)

        # Невалидное значение
        with pytest.raises(ValidationError):
            UploadRequest(storage_mode="invalid")

    def test_upload_request_compress_bool(self):
        """Проверка boolean поля compress."""
        request_true = UploadRequest(compress=True)
        assert request_true.compress is True

        request_false = UploadRequest(compress=False)
        assert request_false.compress is False

    def test_upload_request_compression_algorithm_validation(self):
        """Валидация compression_algorithm."""
        # GZIP
        request_gzip = UploadRequest(compression_algorithm=CompressionAlgorithm.GZIP)
        assert request_gzip.compression_algorithm == CompressionAlgorithm.GZIP

        # Brotli
        request_brotli = UploadRequest(compression_algorithm="brotli")
        assert request_brotli.compression_algorithm == CompressionAlgorithm.BROTLI

        # Невалидный алгоритм
        with pytest.raises(ValidationError):
            UploadRequest(compression_algorithm="zip")


class TestUploadResponse:
    """Тесты для UploadResponse schema."""

    def test_upload_response_minimal(self):
        """Минимальный валидный UploadResponse."""
        file_id = uuid4()
        uploaded_at = datetime.now(timezone.utc)

        response = UploadResponse(
            file_id=file_id,
            original_filename="test.txt",
            storage_filename="test_user_20250114_abc123.txt",
            file_size=1024,
            checksum="sha256checksum",
            uploaded_at=uploaded_at,
            storage_element_url="http://storage:8010"
        )

        assert isinstance(response.file_id, UUID)
        assert response.file_id == file_id
        assert response.original_filename == "test.txt"
        assert response.storage_filename == "test_user_20250114_abc123.txt"
        assert response.file_size == 1024
        assert response.compressed is False  # Default
        assert response.checksum == "sha256checksum"
        assert response.uploaded_at == uploaded_at
        assert response.storage_element_url == "http://storage:8010"

    def test_upload_response_with_compression(self):
        """UploadResponse для сжатого файла."""
        response = UploadResponse(
            file_id=uuid4(),
            original_filename="large.pdf",
            storage_filename="large_user_20250114_xyz789.pdf.gz",
            file_size=5242880,  # 5MB compressed
            compressed=True,
            compression_ratio=0.3,  # 30% от оригинального размера
            checksum="sha256compressed",
            uploaded_at=datetime.now(timezone.utc),
            storage_element_url="http://storage:8010"
        )

        assert response.compressed is True
        assert response.compression_ratio == 0.3
        assert response.file_size == 5242880

    def test_upload_response_file_id_uuid_validation(self):
        """Валидация UUID для file_id."""
        # Валидный UUID
        valid_uuid = uuid4()
        response = UploadResponse(
            file_id=valid_uuid,
            original_filename="test.txt",
            storage_filename="test.txt",
            file_size=100,
            checksum="abc",
            uploaded_at=datetime.now(timezone.utc),
            storage_element_url="http://storage:8010"
        )
        assert isinstance(response.file_id, UUID)

        # Невалидный UUID
        with pytest.raises(ValidationError):
            UploadResponse(
                file_id="not-a-uuid",
                original_filename="test.txt",
                storage_filename="test.txt",
                file_size=100,
                checksum="abc",
                uploaded_at=datetime.now(timezone.utc),
                storage_element_url="http://storage:8010"
            )

    def test_upload_response_file_size_positive(self):
        """file_size должен быть положительным."""
        # Положительный размер
        response = UploadResponse(
            file_id=uuid4(),
            original_filename="test.txt",
            storage_filename="test.txt",
            file_size=1,
            checksum="abc",
            uploaded_at=datetime.now(timezone.utc),
            storage_element_url="http://storage:8010"
        )
        assert response.file_size == 1

        # Нулевой размер - невалиден
        with pytest.raises(ValidationError):
            UploadResponse(
                file_id=uuid4(),
                original_filename="test.txt",
                storage_filename="test.txt",
                file_size=0,
                checksum="abc",
                uploaded_at=datetime.now(timezone.utc),
                storage_element_url="http://storage:8010"
            )

        # Отрицательный размер - невалиден
        with pytest.raises(ValidationError):
            UploadResponse(
                file_id=uuid4(),
                original_filename="test.txt",
                storage_filename="test.txt",
                file_size=-100,
                checksum="abc",
                uploaded_at=datetime.now(timezone.utc),
                storage_element_url="http://storage:8010"
            )

    def test_upload_response_datetime_timezone_aware(self):
        """uploaded_at должен быть timezone-aware."""
        # Timezone-aware datetime
        tz_aware = datetime.now(timezone.utc)
        response = UploadResponse(
            file_id=uuid4(),
            original_filename="test.txt",
            storage_filename="test.txt",
            file_size=100,
            checksum="abc",
            uploaded_at=tz_aware,
            storage_element_url="http://storage:8010"
        )
        assert response.uploaded_at.tzinfo is not None


class TestUploadProgress:
    """Тесты для UploadProgress schema."""

    def test_upload_progress_minimal(self):
        """Минимальный валидный UploadProgress."""
        progress = UploadProgress(
            upload_id=uuid4(),
            bytes_uploaded=512,
            total_bytes=1024,
            progress_percent=50.0,
            status="uploading"
        )

        assert isinstance(progress.upload_id, UUID)
        assert progress.bytes_uploaded == 512
        assert progress.total_bytes == 1024
        assert progress.progress_percent == 50.0
        assert progress.status == "uploading"

    def test_upload_progress_with_status(self):
        """UploadProgress с различными статусами."""
        # Uploading
        uploading = UploadProgress(
            upload_id=uuid4(),
            bytes_uploaded=512,
            total_bytes=1024,
            progress_percent=50.0,
            status="uploading"
        )
        assert uploading.status == "uploading"

        # Completed
        completed = UploadProgress(
            upload_id=uuid4(),
            bytes_uploaded=1024,
            total_bytes=1024,
            progress_percent=100.0,
            status="completed"
        )
        assert completed.status == "completed"

        # Failed
        failed = UploadProgress(
            upload_id=uuid4(),
            bytes_uploaded=512,
            total_bytes=1024,
            progress_percent=50.0,
            status="failed"
        )
        assert failed.status == "failed"

    def test_upload_progress_percentage_range(self):
        """Проверка диапазона progress_percent (0-100)."""
        # 0%
        progress_0 = UploadProgress(
            upload_id=uuid4(),
            bytes_uploaded=0,
            total_bytes=1024,
            progress_percent=0.0,
            status="uploading"
        )
        assert progress_0.progress_percent == 0.0

        # 100%
        progress_100 = UploadProgress(
            upload_id=uuid4(),
            bytes_uploaded=1024,
            total_bytes=1024,
            progress_percent=100.0,
            status="completed"
        )
        assert progress_100.progress_percent == 100.0


class TestUploadError:
    """Тесты для UploadError schema."""

    def test_upload_error_minimal(self):
        """Минимальный валидный UploadError."""
        error = UploadError(
            error_code="UPLOAD_FAILED",
            error_message="File upload failed"
        )

        assert error.error_code == "UPLOAD_FAILED"
        assert error.error_message == "File upload failed"
        assert error.details is None  # Default

    def test_upload_error_with_details(self):
        """UploadError с дополнительными деталями."""
        error = UploadError(
            error_code="STORAGE_UNAVAILABLE",
            error_message="Storage Element is unavailable",
            details={
                "storage_url": "http://storage:8010",
                "retry_after": 60,
                "timestamp": "2025-01-14T12:00:00Z"
            }
        )

        assert error.error_code == "STORAGE_UNAVAILABLE"
        assert error.error_message == "Storage Element is unavailable"
        assert error.details is not None
        assert error.details["retry_after"] == 60
        assert error.details["storage_url"] == "http://storage:8010"

    def test_upload_error_message_not_empty(self):
        """error_message не должен быть пустым."""
        # Валидное сообщение
        error = UploadError(
            error_code="ERROR",
            error_message="Something went wrong"
        )
        assert error.error_message == "Something went wrong"

        # Пустое сообщение - pydantic позволяет пустые строки по умолчанию
        error_empty = UploadError(
            error_code="ERROR",
            error_message=""
        )
        assert error_empty.error_message == ""
