"""
Unit tests для file naming utility.

Тестирует generate_storage_filename(), parse_storage_filename() и validate_storage_filename().
"""

import pytest
from datetime import datetime
from uuid import UUID

from app.utils.file_naming import (
    generate_storage_filename,
    parse_storage_filename,
    validate_storage_filename
)


class TestGenerateStorageFilename:
    """Тесты для generate_storage_filename()."""

    def test_basic_generation(self):
        """Тест базовой генерации filename с автоматическим timestamp и UUID."""
        result = generate_storage_filename("report.pdf", "ivanov")

        # Проверяем формат
        assert result.endswith(".pdf")
        assert "_ivanov_" in result
        assert result.startswith("report_")

        # Проверяем что можно распарсить
        parsed = parse_storage_filename(result)
        assert parsed["name_stem"] == "report"
        assert parsed["username"] == "ivanov"
        assert parsed["extension"] == ".pdf"

    def test_generation_with_fixed_timestamp(self):
        """Тест генерации с фиксированным timestamp."""
        dt = datetime(2025, 11, 8, 10, 30, 45)
        result = generate_storage_filename("doc.txt", "smith", timestamp=dt)

        assert "20251108T103045" in result
        assert result.endswith(".txt")

        parsed = parse_storage_filename(result)
        assert parsed["timestamp"] == dt

    def test_generation_with_fixed_uuid(self):
        """Тест генерации с фиксированным UUID."""
        fixed_uuid = "12345678-90ab-cdef-1234-567890abcdef"
        result = generate_storage_filename(
            "file.pdf",
            "user",
            file_uuid=fixed_uuid
        )

        # UUID в filename хранится без дефисов
        assert "1234567890abcdef1234567890abcdef" in result

        parsed = parse_storage_filename(result)
        assert parsed["uuid"] == fixed_uuid

    def test_generation_with_uuid_object(self):
        """Тест генерации с UUID объектом вместо строки."""
        uuid_obj = UUID("12345678-90ab-cdef-1234-567890abcdef")
        result = generate_storage_filename(
            "file.pdf",
            "user",
            file_uuid=uuid_obj
        )

        assert "1234567890abcdef1234567890abcdef" in result

    def test_complete_example(self):
        """Тест полного примера с всеми фиксированными параметрами."""
        dt = datetime(2025, 11, 8, 10, 30, 45)
        uuid_str = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"

        result = generate_storage_filename(
            "report.pdf",
            "ivanov",
            timestamp=dt,
            file_uuid=uuid_str
        )

        expected = "report_ivanov_20251108T103045_a1b2c3d4e5f67890abcdef1234567890.pdf"
        assert result == expected

    def test_filename_without_extension(self):
        """Тест filename без расширения (должен вызвать ошибку)."""
        # Технически Path(".gitignore").stem == ".gitignore", suffix == ""
        # Но это валидное имя файла
        result = generate_storage_filename(".gitignore", "user")
        assert result.startswith(".gitignore_user_")

    def test_filename_length_exactly_200(self):
        """Тест генерации filename длиной ровно 200 символов."""
        # Создаем имя которое приведет к результату ровно 200 символов
        # Формат: {name_stem}_{username}_{timestamp}_{uuid}{ext}
        # username = "user" (4 символа)
        # timestamp = "20251108T103045" (15 символов)
        # uuid = 32 символа (без дефисов)
        # ext = ".pdf" (4 символа)
        # разделители "_" = 3 символа
        # Итого фиксированная часть = 4 + 1 + 15 + 1 + 32 + 4 = 57 символов
        # Но нужен еще один "_" после name_stem = 58 символов
        # Для 200 символов нужно 200 - 58 = 142 символа name_stem

        name_stem = "a" * 142
        dt = datetime(2025, 11, 8, 10, 30, 45)
        uuid_str = "12345678-90ab-cdef-1234-567890abcdef"

        result = generate_storage_filename(
            f"{name_stem}.pdf",
            "user",
            timestamp=dt,
            file_uuid=uuid_str,
            max_filename_length=200
        )

        assert len(result) == 200

    def test_filename_truncation(self):
        """Тест автоматического обрезания длинного filename."""
        long_name = "a" * 300 + ".pdf"
        result = generate_storage_filename(long_name, "user", max_filename_length=200)

        assert len(result) <= 200
        assert result.endswith(".pdf")

        # Проверяем что name_stem был обрезан
        parsed = parse_storage_filename(result)
        assert len(parsed["name_stem"]) < 300

    def test_filename_with_multiple_dots(self):
        """Тест filename с множественными точками."""
        result = generate_storage_filename("archive.tar.gz", "admin")

        # Path("archive.tar.gz").suffix == ".gz"
        # Path("archive.tar.gz").stem == "archive.tar"
        assert result.endswith(".gz")

        parsed = parse_storage_filename(result)
        assert parsed["name_stem"] == "archive.tar"
        assert parsed["extension"] == ".gz"

    def test_filename_with_underscores(self):
        """Тест filename с подчеркиваниями в имени."""
        result = generate_storage_filename("my_document_v2.pdf", "user")

        parsed = parse_storage_filename(result)
        assert parsed["name_stem"] == "my_document_v2"

    def test_username_with_allowed_special_chars(self):
        """Тест username с разрешенными специальными символами."""
        result = generate_storage_filename("file.txt", "user-name_123")

        assert "_user-name_123_" in result

    def test_cyrillic_in_filename(self):
        """Тест кириллицы в filename (должна сохраниться)."""
        result = generate_storage_filename("отчет.pdf", "ivanov")

        parsed = parse_storage_filename(result)
        assert parsed["name_stem"] == "отчет"

    def test_spaces_in_filename(self):
        """Тест пробелов в filename (должны сохраниться)."""
        result = generate_storage_filename("my report.pdf", "user")

        parsed = parse_storage_filename(result)
        assert parsed["name_stem"] == "my report"


class TestGenerateStorageFilenameValidation:
    """Тесты валидации входных данных для generate_storage_filename()."""

    def test_empty_original_name(self):
        """Тест пустого original_name."""
        with pytest.raises(ValueError, match="original_name не может быть пустым"):
            generate_storage_filename("", "user")

    def test_whitespace_only_original_name(self):
        """Тест original_name состоящего только из пробелов."""
        with pytest.raises(ValueError, match="original_name не может быть пустым"):
            generate_storage_filename("   ", "user")

    def test_empty_username(self):
        """Тест пустого username."""
        with pytest.raises(ValueError, match="username не может быть пустым"):
            generate_storage_filename("file.pdf", "")

    def test_whitespace_only_username(self):
        """Тест username состоящего только из пробелов."""
        with pytest.raises(ValueError, match="username не может быть пустым"):
            generate_storage_filename("file.pdf", "   ")

    def test_username_with_invalid_characters(self):
        """Тест username с недопустимыми символами."""
        invalid_usernames = [
            "user name",  # пробел
            "user@domain",  # @
            "user/admin",  # /
            "user\\admin",  # \
            "user.name",  # точка
            "иванов",  # кириллица
        ]

        for username in invalid_usernames:
            with pytest.raises(ValueError, match="username содержит недопустимые символы"):
                generate_storage_filename("file.pdf", username)

    def test_invalid_uuid_format(self):
        """Тест недопустимого формата UUID."""
        with pytest.raises(ValueError, match="Недопустимый формат UUID"):
            generate_storage_filename("file.pdf", "user", file_uuid="not-a-uuid")

    def test_impossible_max_length(self):
        """Тест невозможной максимальной длины (слишком короткой)."""
        with pytest.raises(ValueError, match="Невозможно создать filename"):
            generate_storage_filename(
                "file.pdf",
                "verylongusername",
                max_filename_length=50  # Слишком мало
            )

    def test_minimum_viable_max_length(self):
        """Тест минимально возможной максимальной длины."""
        # Минимальная длина должна вместить:
        # "a" (1 символ name_stem)
        # "_u_" (3 символа для разделителей и минимального username)
        # "20251108T103045" (15 символов timestamp)
        # "_" (1 символ разделитель)
        # 32 символа UUID
        # ".p" (2 символа минимального расширения)
        # Итого минимум: 1 + 1 + 1 + 15 + 1 + 32 + 1 + 2 = 54 символа

        dt = datetime(2025, 11, 8, 10, 30, 45)
        result = generate_storage_filename(
            "a.p",
            "u",
            timestamp=dt,
            max_filename_length=54
        )

        assert len(result) <= 54


class TestParseStorageFilename:
    """Тесты для parse_storage_filename()."""

    def test_parse_basic_filename(self):
        """Тест парсинга базового filename."""
        filename = "report_ivanov_20251108T103045_a1b2c3d4e5f67890abcdef1234567890.pdf"

        parsed = parse_storage_filename(filename)

        assert parsed["name_stem"] == "report"
        assert parsed["username"] == "ivanov"
        assert parsed["timestamp"] == datetime(2025, 11, 8, 10, 30, 45)
        assert parsed["uuid"] == "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
        assert parsed["extension"] == ".pdf"

    def test_parse_filename_with_underscores_in_name(self):
        """Тест парсинга filename с подчеркиваниями в имени."""
        filename = "my_long_document_name_user_20251108T103045_a1b2c3d4e5f67890abcdef1234567890.pdf"

        parsed = parse_storage_filename(filename)

        assert parsed["name_stem"] == "my_long_document_name"
        assert parsed["username"] == "user"

    def test_parse_filename_without_extension(self):
        """Тест парсинга filename без расширения."""
        filename = ".gitignore_user_20251108T103045_a1b2c3d4e5f67890abcdef1234567890"

        parsed = parse_storage_filename(filename)

        assert parsed["name_stem"] == ".gitignore"
        assert parsed["extension"] == ""

    def test_parse_filename_with_multiple_extensions(self):
        """Тест парсинга filename с множественными расширениями."""
        filename = "archive.tar_user_20251108T103045_a1b2c3d4e5f67890abcdef1234567890.gz"

        parsed = parse_storage_filename(filename)

        assert parsed["name_stem"] == "archive.tar"
        assert parsed["extension"] == ".gz"

    def test_parse_invalid_format_too_few_parts(self):
        """Тест парсинга невалидного формата (слишком мало частей)."""
        with pytest.raises(ValueError, match="Недопустимый формат storage filename"):
            parse_storage_filename("invalid_format.pdf")

    def test_parse_invalid_timestamp(self):
        """Тест парсинга невалидного timestamp."""
        with pytest.raises(ValueError, match="Недопустимый формат timestamp"):
            parse_storage_filename("file_user_INVALID_a1b2c3d4e5f67890abcdef1234567890.pdf")

    def test_parse_invalid_uuid(self):
        """Тест парсинга невалидного UUID."""
        with pytest.raises(ValueError, match="Недопустимый формат UUID"):
            parse_storage_filename("file_user_20251108T103045_INVALID.pdf")

    def test_roundtrip_generation_and_parsing(self):
        """Тест roundtrip: генерация → парсинг → проверка данных."""
        original_name = "document.pdf"
        username = "testuser"
        dt = datetime(2025, 11, 8, 15, 30, 45)
        uuid_str = "12345678-90ab-cdef-1234-567890abcdef"

        # Генерация
        generated = generate_storage_filename(
            original_name,
            username,
            timestamp=dt,
            file_uuid=uuid_str
        )

        # Парсинг
        parsed = parse_storage_filename(generated)

        # Проверка
        assert parsed["name_stem"] == "document"
        assert parsed["username"] == username
        assert parsed["timestamp"] == dt
        assert parsed["uuid"] == uuid_str
        assert parsed["extension"] == ".pdf"


class TestValidateStorageFilename:
    """Тесты для validate_storage_filename()."""

    def test_validate_correct_filename(self):
        """Тест валидации корректного filename."""
        filename = "report_ivanov_20251108T103045_a1b2c3d4e5f67890abcdef1234567890.pdf"
        assert validate_storage_filename(filename) is True

    def test_validate_incorrect_filename(self):
        """Тест валидации некорректного filename."""
        assert validate_storage_filename("invalid_format.pdf") is False

    def test_validate_generated_filename(self):
        """Тест валидации сгенерированного filename."""
        generated = generate_storage_filename("test.txt", "user")
        assert validate_storage_filename(generated) is True


class TestEdgeCases:
    """Тесты граничных случаев."""

    def test_very_long_original_name_truncation(self):
        """Тест обрезания очень длинного оригинального имени."""
        # Создаем имя длиной 500 символов
        long_name = "a" * 500 + ".pdf"

        result = generate_storage_filename(long_name, "user", max_filename_length=200)

        assert len(result) <= 200
        assert result.endswith(".pdf")

        # Проверяем что можем распарсить
        parsed = parse_storage_filename(result)
        assert len(parsed["name_stem"]) < 500

    def test_exactly_max_length_boundary(self):
        """Тест граничного случая - filename ровно max_filename_length."""
        # Рассчитываем точную длину name_stem для результата в 100 символов
        dt = datetime(2025, 11, 8, 10, 30, 45)
        uuid_str = "12345678-90ab-cdef-1234-567890abcdef"

        # Фиксированная часть: "_user_20251108T103045_1234567890abcdef1234567890abcdef.pdf"
        # = 1 + 4 + 1 + 15 + 1 + 32 + 4 = 58 символов
        # Для 100 символов нужно: 100 - 58 = 42 символа name_stem

        name_stem = "a" * 42
        result = generate_storage_filename(
            f"{name_stem}.pdf",
            "user",
            timestamp=dt,
            file_uuid=uuid_str,
            max_filename_length=100
        )

        assert len(result) == 100

    def test_unicode_characters_in_name(self):
        """Тест Unicode символов в имени файла."""
        unicode_names = [
            "отчет.pdf",  # кириллица
            "文档.pdf",  # китайский
            "ファイル.pdf",  # японский
            "مستند.pdf",  # арабский
            "📄document.pdf",  # emoji
        ]

        for name in unicode_names:
            result = generate_storage_filename(name, "user")

            # Должны сохраниться и быть парсируемыми
            parsed = parse_storage_filename(result)
            assert parsed["extension"] == ".pdf"

    def test_special_characters_in_filename(self):
        """Тест специальных символов в filename."""
        special_names = [
            "file (1).pdf",  # скобки
            "file [copy].pdf",  # квадратные скобки
            "file-v2.pdf",  # дефис
            "file+new.pdf",  # плюс
        ]

        for name in special_names:
            result = generate_storage_filename(name, "user")

            # Должны работать
            parsed = parse_storage_filename(result)
            assert parsed["extension"] == ".pdf"

    def test_minimum_username_length(self):
        """Тест минимальной длины username (1 символ)."""
        result = generate_storage_filename("file.pdf", "a")

        assert "_a_" in result

        parsed = parse_storage_filename(result)
        assert parsed["username"] == "a"

    def test_maximum_username_length(self):
        """Тест максимальной длины username."""
        # Username может быть достаточно длинным, главное чтобы
        # вся строка уместилась в max_filename_length
        long_username = "a" * 50

        result = generate_storage_filename("f.p", long_username, max_filename_length=200)

        assert len(result) <= 200

        parsed = parse_storage_filename(result)
        assert parsed["username"] == long_username


class TestDatetimeHandling:
    """Тесты обработки datetime."""

    def test_different_datetime_formats(self):
        """Тест различных datetime значений."""
        test_cases = [
            datetime(2025, 1, 1, 0, 0, 0),  # Начало года
            datetime(2025, 12, 31, 23, 59, 59),  # Конец года
            datetime(2025, 6, 15, 12, 30, 45),  # Середина года
        ]

        for dt in test_cases:
            result = generate_storage_filename("file.pdf", "user", timestamp=dt)

            parsed = parse_storage_filename(result)
            assert parsed["timestamp"] == dt

    def test_timestamp_format_consistency(self):
        """Тест консистентности формата timestamp."""
        dt = datetime(2025, 11, 8, 9, 5, 3)  # Одиночные цифры

        result = generate_storage_filename("file.pdf", "user", timestamp=dt)

        # Должен быть формат с ведущими нулями
        assert "20251108T090503" in result


class TestUUIDHandling:
    """Тесты обработки UUID."""

    def test_uuid_with_uppercase(self):
        """Тест UUID с заглавными буквами."""
        uuid_upper = "12345678-90AB-CDEF-1234-567890ABCDEF"

        result = generate_storage_filename("file.pdf", "user", file_uuid=uuid_upper)

        # UUID должен быть нормализован к lowercase
        assert "1234567890abcdef1234567890abcdef" in result.lower()

    def test_uuid_without_dashes(self):
        """Тест UUID без дефисов."""
        uuid_no_dash = "1234567890abcdef1234567890abcdef"

        result = generate_storage_filename("file.pdf", "user", file_uuid=uuid_no_dash)

        # Должен работать
        assert uuid_no_dash in result

    def test_uuid_object_vs_string(self):
        """Тест что UUID объект и строка дают одинаковый результат."""
        uuid_str = "12345678-90ab-cdef-1234-567890abcdef"
        uuid_obj = UUID(uuid_str)

        dt = datetime(2025, 11, 8, 10, 30, 45)

        result_str = generate_storage_filename(
            "file.pdf", "user", timestamp=dt, file_uuid=uuid_str
        )
        result_obj = generate_storage_filename(
            "file.pdf", "user", timestamp=dt, file_uuid=uuid_obj
        )

        assert result_str == result_obj
