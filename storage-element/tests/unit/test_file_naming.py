"""
Unit tests для app/utils/file_naming.py

Тестируемые компоненты:
- sanitize_filename(): очистка имен от недопустимых символов
- truncate_stem(): обрезание длинных имен
- generate_storage_filename(): генерация уникальных имен
- generate_storage_path(): генерация путей по дате
- parse_storage_filename(): парсинг storage имен
"""

import pytest
from datetime import datetime
from uuid import UUID

from app.utils.file_naming import (
    sanitize_filename,
    truncate_stem,
    generate_storage_filename,
    generate_storage_path,
    parse_storage_filename
)


# ==========================================
# Test sanitize_filename
# ==========================================

class TestSanitizeFilename:
    """Тесты для sanitize_filename()"""

    def test_sanitize_basic_filename(self):
        """Базовое имя без недопустимых символов"""
        assert sanitize_filename("document.pdf") == "document.pdf"
        assert sanitize_filename("report_2024.docx") == "report_2024.docx"

    def test_sanitize_with_invalid_chars(self):
        """Замена недопустимых символов на подчеркивание"""
        assert sanitize_filename("report/2024.pdf") == "report_2024.pdf"
        assert sanitize_filename("file<name>.txt") == "file_name_.txt"
        assert sanitize_filename("file:name?.doc") == "file_name_.doc"

    def test_sanitize_unicode_characters(self):
        """Сохранение unicode символов (русский, китайский)"""
        assert sanitize_filename("отчет 2024.pdf") == "отчет_2024.pdf"
        assert sanitize_filename("文档.txt") == "文档.txt"

    def test_sanitize_multiple_underscores(self):
        """Замена множественных подчеркиваний на одно"""
        assert sanitize_filename("file___name.txt") == "file_name.txt"
        assert sanitize_filename("a/b/c.pdf") == "a_b_c.pdf"

    def test_sanitize_leading_trailing_underscores(self):
        """Удаление подчеркиваний в начале и конце"""
        assert sanitize_filename("_filename_.txt") == "filename_.txt"
        assert sanitize_filename("/filename/") == "filename"

    def test_sanitize_empty_string(self):
        """Пустая строка после очистки"""
        assert sanitize_filename("") == ""
        assert sanitize_filename("///") == ""


# ==========================================
# Test truncate_stem
# ==========================================

class TestTruncateStem:
    """Тесты для truncate_stem()"""

    def test_truncate_short_stem(self):
        """Короткие имена не обрезаются"""
        assert truncate_stem("short", 10) == "short"
        assert truncate_stem("file", 4) == "file"

    def test_truncate_long_stem(self):
        """Длинные имена обрезаются с многоточием"""
        assert truncate_stem("very_long_filename", 10) == "very_lo..."
        assert truncate_stem("document", 5) == "do..."

    def test_truncate_exact_length(self):
        """Имя точно равное max_length не обрезается"""
        assert truncate_stem("filename", 8) == "filename"

    def test_truncate_minimum_length(self):
        """Минимальная длина (3 символа для '...')"""
        assert truncate_stem("file", 3) == "..."
        with pytest.raises(IndexError):
            truncate_stem("file", 2)


# ==========================================
# Test generate_storage_filename
# ==========================================

class TestGenerateStorageFilename:
    """Тесты для generate_storage_filename()"""

    def test_generate_basic_filename(self):
        """Базовая генерация с заданными параметрами"""
        timestamp = datetime(2025, 1, 10, 15, 30, 45)
        file_uuid = UUID("a1b2c3d4-e5f6-7890-abcd-ef1234567890")

        result = generate_storage_filename(
            "report.pdf",
            "ivanov",
            timestamp,
            file_uuid
        )

        assert result == "report_ivanov_20250110T153045_a1b2c3d4-e5f6-7890-abcd-ef1234567890.pdf"

    def test_generate_with_defaults(self):
        """Генерация с default timestamp и UUID"""
        result = generate_storage_filename("document.txt", "user")

        # Проверка формата
        parts = result.split('_')
        assert len(parts) >= 4
        assert parts[0] == "document"
        assert parts[1] == "user"
        # Timestamp должен быть в формате YYYYMMDDTHHMMSS
        assert len(parts[2]) == 15
        assert parts[2][8] == 'T'

    def test_generate_with_unicode_filename(self):
        """Генерация с unicode именем файла"""
        timestamp = datetime(2025, 1, 10, 15, 30, 45)
        file_uuid = UUID("a1b2c3d4-e5f6-7890-abcd-ef1234567890")

        result = generate_storage_filename(
            "отчет.pdf",
            "иванов",
            timestamp,
            file_uuid
        )

        assert result.startswith("отчет_иванов_")
        assert result.endswith(".pdf")

    def test_generate_truncates_long_filename(self):
        """Обрезание длинного имени файла"""
        long_name = "very_long_document_name_that_exceeds_maximum_allowed_length" * 5
        timestamp = datetime(2025, 1, 10, 15, 30, 45)
        file_uuid = UUID("a1b2c3d4-e5f6-7890-abcd-ef1234567890")

        result = generate_storage_filename(
            f"{long_name}.pdf",
            "user",
            timestamp,
            file_uuid,
            max_total_length=200
        )

        assert len(result) <= 200
        assert result.endswith(".pdf")

    def test_generate_invalid_username(self):
        """Валидация пустого или недопустимого username"""
        with pytest.raises(ValueError, match="Username cannot be empty"):
            generate_storage_filename("file.txt", "")

        with pytest.raises(ValueError, match="Username cannot be empty"):
            generate_storage_filename("file.txt", "   ")

    def test_generate_username_with_invalid_chars(self):
        """Username с недопустимыми символами очищается"""
        timestamp = datetime(2025, 1, 10, 15, 30, 45)
        file_uuid = UUID("a1b2c3d4-e5f6-7890-abcd-ef1234567890")

        result = generate_storage_filename(
            "file.txt",
            "user/name",
            timestamp,
            file_uuid
        )

        assert "user_name" in result

    def test_generate_filename_only_invalid_chars(self):
        """Файл содержащий только недопустимые символы"""
        timestamp = datetime(2025, 1, 10, 15, 30, 45)
        file_uuid = UUID("a1b2c3d4-e5f6-7890-abcd-ef1234567890")

        result = generate_storage_filename(
            "///.pdf",
            "user",
            timestamp,
            file_uuid
        )

        # Должен использовать "file" как fallback
        assert result.startswith("file_user_")

    def test_generate_various_extensions(self):
        """Различные расширения файлов"""
        timestamp = datetime(2025, 1, 10, 15, 30, 45)
        file_uuid = UUID("a1b2c3d4-e5f6-7890-abcd-ef1234567890")

        for ext in [".pdf", ".docx", ".txt", ".jpg", ".zip", ""]:
            result = generate_storage_filename(
                f"file{ext}",
                "user",
                timestamp,
                file_uuid
            )
            assert result.endswith(ext)


# ==========================================
# Test generate_storage_path
# ==========================================

class TestGenerateStoragePath:
    """Тесты для generate_storage_path()"""

    def test_generate_path_with_timestamp(self):
        """Генерация пути с заданным timestamp"""
        timestamp = datetime(2025, 1, 10, 15, 30, 45)
        result = generate_storage_path(timestamp)

        assert result == "2025/01/10/15/"

    def test_generate_path_with_default(self):
        """Генерация пути с текущим временем"""
        result = generate_storage_path()

        # Проверка формата YYYY/MM/DD/HH/
        parts = result.split('/')
        assert len(parts) == 5  # year/month/day/hour/''
        assert len(parts[0]) == 4  # год
        assert len(parts[1]) == 2  # месяц
        assert len(parts[2]) == 2  # день
        assert len(parts[3]) == 2  # час

    def test_generate_path_different_times(self):
        """Разные времена генерируют разные пути"""
        path1 = generate_storage_path(datetime(2025, 1, 10, 15, 0, 0))
        path2 = generate_storage_path(datetime(2025, 1, 10, 16, 0, 0))

        assert path1 != path2
        assert path1 == "2025/01/10/15/"
        assert path2 == "2025/01/10/16/"


# ==========================================
# Test parse_storage_filename
# ==========================================

class TestParseStorageFilename:
    """Тесты для parse_storage_filename()"""

    def test_parse_valid_filename(self):
        """Парсинг валидного storage filename"""
        filename = "report_ivanov_20250110T153045_a1b2c3d4-e5f6-7890-abcd-ef1234567890.pdf"

        result = parse_storage_filename(filename)

        assert result["original_stem"] == "report"
        assert result["username"] == "ivanov"
        assert result["timestamp"] == datetime(2025, 1, 10, 15, 30, 45)
        assert result["uuid"] == UUID("a1b2c3d4-e5f6-7890-abcd-ef1234567890")
        assert result["extension"] == ".pdf"

    def test_parse_filename_with_underscores_in_stem(self):
        """Парсинг имени с подчеркиваниями в original stem"""
        filename = "my_long_report_name_user_20250110T153045_a1b2c3d4-e5f6-7890-abcd-ef1234567890.pdf"

        result = parse_storage_filename(filename)

        assert result["original_stem"] == "my_long_report_name"
        assert result["username"] == "user"

    def test_parse_filename_unicode(self):
        """Парсинг имени с unicode символами"""
        filename = "отчет_иванов_20250110T153045_a1b2c3d4-e5f6-7890-abcd-ef1234567890.pdf"

        result = parse_storage_filename(filename)

        assert result["original_stem"] == "отчет"
        assert result["username"] == "иванов"

    def test_parse_filename_no_extension(self):
        """Парсинг имени без расширения"""
        filename = "file_user_20250110T153045_a1b2c3d4-e5f6-7890-abcd-ef1234567890"

        result = parse_storage_filename(filename)

        assert result["extension"] == ""

    def test_parse_invalid_format(self):
        """Парсинг невалидного формата"""
        with pytest.raises(ValueError, match="Invalid storage filename format"):
            parse_storage_filename("invalid_filename.pdf")

        with pytest.raises(ValueError, match="Invalid storage filename format"):
            parse_storage_filename("only_two_parts.pdf")

    def test_parse_invalid_timestamp(self):
        """Парсинг с невалидным timestamp"""
        with pytest.raises(ValueError, match="Invalid timestamp format"):
            parse_storage_filename("file_user_invalid_timestamp_a1b2c3d4-e5f6-7890-abcd-ef1234567890.pdf")

    def test_parse_invalid_uuid(self):
        """Парсинг с невалидным UUID"""
        with pytest.raises(ValueError, match="Invalid UUID format"):
            parse_storage_filename("file_user_20250110T153045_invalid_uuid.pdf")


# ==========================================
# Integration Tests
# ==========================================

class TestFileNamingIntegration:
    """Интеграционные тесты для file naming utilities"""

    def test_generate_and_parse_roundtrip(self):
        """Генерация и парсинг - полный цикл"""
        original_filename = "my_document.pdf"
        username = "testuser"
        timestamp = datetime(2025, 1, 10, 15, 30, 45)
        file_uuid = UUID("a1b2c3d4-e5f6-7890-abcd-ef1234567890")

        # Генерация
        storage_filename = generate_storage_filename(
            original_filename,
            username,
            timestamp,
            file_uuid
        )

        # Парсинг
        parsed = parse_storage_filename(storage_filename)

        # Проверка roundtrip
        assert parsed["original_stem"] == "my_document"
        assert parsed["username"] == username
        assert parsed["timestamp"] == timestamp
        assert parsed["uuid"] == file_uuid
        assert parsed["extension"] == ".pdf"

    def test_generate_with_path(self):
        """Генерация filename + path"""
        timestamp = datetime(2025, 1, 10, 15, 30, 45)
        file_uuid = UUID("a1b2c3d4-e5f6-7890-abcd-ef1234567890")

        filename = generate_storage_filename(
            "report.pdf",
            "user",
            timestamp,
            file_uuid
        )
        path = generate_storage_path(timestamp)

        # Полный путь к файлу
        full_path = path + filename

        assert full_path == "2025/01/10/15/report_user_20250110T153045_a1b2c3d4-e5f6-7890-abcd-ef1234567890.pdf"
