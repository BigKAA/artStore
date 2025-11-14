"""
Unit tests для app/utils/attr_utils.py

Тестируемые компоненты:
- FileAttributes: Pydantic модель для атрибутов
- write_attr_file(): Атомарная запись attr.json
- read_attr_file(): Чтение и валидация attr.json
- delete_attr_file(): Удаление attr.json
- get_attr_file_path(): Получение пути к attr.json
- verify_attr_file_consistency(): Проверка консистентности
"""

import json
import pytest
from datetime import datetime
from pathlib import Path
from uuid import UUID, uuid4

from app.utils.attr_utils import (
    FileAttributes,
    MAX_ATTR_FILE_SIZE,
    write_attr_file,
    read_attr_file,
    delete_attr_file,
    get_attr_file_path,
    verify_attr_file_consistency
)
from app.core.exceptions import InvalidAttributeFileException


# ==========================================
# Test FileAttributes Model
# ==========================================

class TestFileAttributesModel:
    """Тесты для Pydantic модели FileAttributes"""

    def test_create_valid_attributes(self):
        """Создание валидных атрибутов"""
        attrs = FileAttributes(
            file_id=uuid4(),
            original_filename="document.pdf",
            storage_filename="document_user_20250111T120000_abc123.pdf",
            file_size=1024,
            content_type="application/pdf",
            created_at=datetime.now(),
            updated_at=datetime.now(),
            created_by_id="user123",
            created_by_username="testuser",
            storage_path="2025/01/11/12/document_user_20250111T120000_abc123.pdf",
            checksum="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
        )

        assert attrs.file_size == 1024
        assert attrs.original_filename == "document.pdf"

    def test_validate_file_size_positive(self):
        """Валидация положительного размера файла"""
        from pydantic import ValidationError

        with pytest.raises(ValidationError, match="Input should be greater than 0"):
            FileAttributes(
                file_id=uuid4(),
                original_filename="file.pdf",
                storage_filename="file_user_20250111T120000_abc123.pdf",
                file_size=0,  # Невалидный размер
                content_type="application/pdf",
                created_at=datetime.now(),
                updated_at=datetime.now(),
                created_by_id="user123",
                created_by_username="testuser",
                storage_path="2025/01/11/12/file.pdf",
                checksum="a" * 64
            )

    def test_validate_checksum_length(self):
        """Валидация длины SHA256 checksum (64 символа)"""
        with pytest.raises(ValueError, match="Checksum must be 64 characters"):
            FileAttributes(
                file_id=uuid4(),
                original_filename="file.pdf",
                storage_filename="file_user_20250111T120000_abc123.pdf",
                file_size=1024,
                content_type="application/pdf",
                created_at=datetime.now(),
                updated_at=datetime.now(),
                created_by_id="user123",
                created_by_username="testuser",
                storage_path="2025/01/11/12/file.pdf",
                checksum="short"  # Слишком короткий
            )

    def test_validate_checksum_hex(self):
        """Валидация что checksum - hexadecimal строка"""
        with pytest.raises(ValueError, match="Checksum must be hexadecimal"):
            FileAttributes(
                file_id=uuid4(),
                original_filename="file.pdf",
                storage_filename="file_user_20250111T120000_abc123.pdf",
                file_size=1024,
                content_type="application/pdf",
                created_at=datetime.now(),
                updated_at=datetime.now(),
                created_by_id="user123",
                created_by_username="testuser",
                storage_path="2025/01/11/12/file.pdf",
                checksum="z" * 64  # Не hex символы
            )

    def test_optional_fields(self):
        """Опциональные поля могут быть None"""
        attrs = FileAttributes(
            file_id=uuid4(),
            original_filename="file.pdf",
            storage_filename="file_user_20250111T120000_abc123.pdf",
            file_size=1024,
            content_type="application/pdf",
            created_at=datetime.now(),
            updated_at=datetime.now(),
            created_by_id="user123",
            created_by_username="testuser",
            storage_path="2025/01/11/12/file.pdf",
            checksum="a" * 64,
            # Опциональные поля не указаны
            created_by_fullname=None,
            description=None,
            version=None,
            metadata=None
        )

        assert attrs.created_by_fullname is None
        assert attrs.description is None
        assert attrs.metadata is None  # Явно передан None

    def test_metadata_default_factory(self):
        """Metadata использует default_factory когда не передан явно"""
        attrs = FileAttributes(
            file_id=uuid4(),
            original_filename="file.pdf",
            storage_filename="file_user_20250111T120000_abc123.pdf",
            file_size=1024,
            content_type="application/pdf",
            created_at=datetime.now(),
            updated_at=datetime.now(),
            created_by_id="user123",
            created_by_username="testuser",
            storage_path="2025/01/11/12/file.pdf",
            checksum="a" * 64
            # metadata НЕ передан - должен использоваться default_factory
        )

        assert attrs.metadata == {}  # Default factory dict

    def test_metadata_field(self):
        """Поле metadata может содержать произвольные данные"""
        attrs = FileAttributes(
            file_id=uuid4(),
            original_filename="file.pdf",
            storage_filename="file_user_20250111T120000_abc123.pdf",
            file_size=1024,
            content_type="application/pdf",
            created_at=datetime.now(),
            updated_at=datetime.now(),
            created_by_id="user123",
            created_by_username="testuser",
            storage_path="2025/01/11/12/file.pdf",
            checksum="a" * 64,
            metadata={
                "department": "Sales",
                "project": "Q1-2025",
                "tags": ["important", "contract"]
            }
        )

        assert attrs.metadata["department"] == "Sales"
        assert len(attrs.metadata["tags"]) == 2


# ==========================================
# Test write_attr_file
# ==========================================

class TestWriteAttrFile:
    """Тесты для write_attr_file()"""

    @pytest.mark.asyncio
    async def test_write_valid_attr_file(self, temp_storage_dir):
        """Запись валидного файла атрибутов"""
        attr_path = temp_storage_dir / "test.pdf.attr.json"

        attrs = FileAttributes(
            file_id=uuid4(),
            original_filename="test.pdf",
            storage_filename="test_user_20250111T120000_abc123.pdf",
            file_size=1024,
            content_type="application/pdf",
            created_at=datetime.now(),
            updated_at=datetime.now(),
            created_by_id="user123",
            created_by_username="testuser",
            storage_path="2025/01/11/12/test.pdf",
            checksum="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
        )

        await write_attr_file(attr_path, attrs)

        # Проверка что файл создан
        assert attr_path.exists()

        # Проверка что размер в пределах лимита
        assert attr_path.stat().st_size <= MAX_ATTR_FILE_SIZE

        # Проверка что JSON валиден
        data = json.loads(attr_path.read_text())
        assert data["original_filename"] == "test.pdf"

    @pytest.mark.asyncio
    async def test_write_creates_parent_directories(self, temp_storage_dir):
        """Запись создает родительские директории"""
        attr_path = temp_storage_dir / "subdir1" / "subdir2" / "test.pdf.attr.json"

        attrs = FileAttributes(
            file_id=uuid4(),
            original_filename="test.pdf",
            storage_filename="test_user_20250111T120000_abc123.pdf",
            file_size=1024,
            content_type="application/pdf",
            created_at=datetime.now(),
            updated_at=datetime.now(),
            created_by_id="user123",
            created_by_username="testuser",
            storage_path="2025/01/11/12/test.pdf",
            checksum="a" * 64
        )

        await write_attr_file(attr_path, attrs)

        assert attr_path.exists()
        assert attr_path.parent.exists()

    @pytest.mark.asyncio
    async def test_write_overwrites_existing_file(self, temp_storage_dir):
        """Запись перезаписывает существующий файл"""
        attr_path = temp_storage_dir / "test.pdf.attr.json"

        # Первая запись
        attrs1 = FileAttributes(
            file_id=uuid4(),
            original_filename="test.pdf",
            storage_filename="test_user_20250111T120000_abc123.pdf",
            file_size=1024,
            content_type="application/pdf",
            created_at=datetime.now(),
            updated_at=datetime.now(),
            created_by_id="user123",
            created_by_username="testuser",
            storage_path="2025/01/11/12/test.pdf",
            checksum="a" * 64
        )

        await write_attr_file(attr_path, attrs1)
        assert attr_path.exists()

        # Вторая запись (перезапись)
        attrs2 = FileAttributes(
            file_id=uuid4(),
            original_filename="updated.pdf",
            storage_filename="updated_user_20250111T120000_xyz789.pdf",
            file_size=2048,
            content_type="application/pdf",
            created_at=datetime.now(),
            updated_at=datetime.now(),
            created_by_id="user123",
            created_by_username="testuser",
            storage_path="2025/01/11/12/updated.pdf",
            checksum="b" * 64
        )

        await write_attr_file(attr_path, attrs2)

        # Проверка что файл обновлен
        data = json.loads(attr_path.read_text())
        assert data["original_filename"] == "updated.pdf"
        assert data["file_size"] == 2048

    @pytest.mark.asyncio
    async def test_write_exceeds_size_limit(self, temp_storage_dir):
        """Запись файла превышающего лимит 4KB"""
        attr_path = temp_storage_dir / "test.pdf.attr.json"

        # Создание огромного metadata для превышения лимита
        huge_metadata = {"data": "x" * (MAX_ATTR_FILE_SIZE + 1000)}

        attrs = FileAttributes(
            file_id=uuid4(),
            original_filename="test.pdf",
            storage_filename="test_user_20250111T120000_abc123.pdf",
            file_size=1024,
            content_type="application/pdf",
            created_at=datetime.now(),
            updated_at=datetime.now(),
            created_by_id="user123",
            created_by_username="testuser",
            storage_path="2025/01/11/12/test.pdf",
            checksum="a" * 64,
            metadata=huge_metadata
        )

        with pytest.raises(InvalidAttributeFileException, match="exceeds maximum"):
            await write_attr_file(attr_path, attrs)

        # Файл не должен быть создан
        assert not attr_path.exists()


# ==========================================
# Test read_attr_file
# ==========================================

class TestReadAttrFile:
    """Тесты для read_attr_file()"""

    @pytest.mark.asyncio
    async def test_read_valid_attr_file(self, temp_storage_dir):
        """Чтение валидного файла атрибутов"""
        attr_path = temp_storage_dir / "test.pdf.attr.json"

        # Создание файла
        file_id = uuid4()
        attrs_write = FileAttributes(
            file_id=file_id,
            original_filename="test.pdf",
            storage_filename="test_user_20250111T120000_abc123.pdf",
            file_size=1024,
            content_type="application/pdf",
            created_at=datetime.now(),
            updated_at=datetime.now(),
            created_by_id="user123",
            created_by_username="testuser",
            storage_path="2025/01/11/12/test.pdf",
            checksum="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
        )

        await write_attr_file(attr_path, attrs_write)

        # Чтение файла
        attrs_read = await read_attr_file(attr_path)

        assert attrs_read.file_id == file_id
        assert attrs_read.original_filename == "test.pdf"
        assert attrs_read.file_size == 1024

    @pytest.mark.asyncio
    async def test_read_nonexistent_file(self, temp_storage_dir):
        """Чтение несуществующего файла"""
        attr_path = temp_storage_dir / "nonexistent.pdf.attr.json"

        with pytest.raises(FileNotFoundError):
            await read_attr_file(attr_path)

    @pytest.mark.asyncio
    async def test_read_invalid_json(self, temp_storage_dir):
        """Чтение файла с невалидным JSON"""
        attr_path = temp_storage_dir / "test.pdf.attr.json"

        # Создание файла с невалидным JSON
        attr_path.write_text("{ invalid json }", encoding='utf-8')

        with pytest.raises(InvalidAttributeFileException, match="Invalid JSON format"):
            await read_attr_file(attr_path)

    @pytest.mark.asyncio
    async def test_read_invalid_schema(self, temp_storage_dir):
        """Чтение файла с невалидной схемой"""
        attr_path = temp_storage_dir / "test.pdf.attr.json"

        # Создание файла с валидным JSON но невалидной схемой
        invalid_data = {
            "file_id": str(uuid4()),
            "original_filename": "test.pdf"
            # Пропущены обязательные поля
        }
        attr_path.write_text(json.dumps(invalid_data), encoding='utf-8')

        with pytest.raises(InvalidAttributeFileException, match="Failed to parse attributes"):
            await read_attr_file(attr_path)

    @pytest.mark.asyncio
    async def test_read_exceeds_size_limit(self, temp_storage_dir):
        """Чтение файла превышающего лимит"""
        attr_path = temp_storage_dir / "test.pdf.attr.json"

        # Создание файла больше 4KB
        large_data = "x" * (MAX_ATTR_FILE_SIZE + 1000)
        attr_path.write_text(large_data, encoding='utf-8')

        with pytest.raises(InvalidAttributeFileException, match="exceeds maximum"):
            await read_attr_file(attr_path)


# ==========================================
# Test delete_attr_file
# ==========================================

class TestDeleteAttrFile:
    """Тесты для delete_attr_file()"""

    @pytest.mark.asyncio
    async def test_delete_existing_file(self, temp_storage_dir):
        """Удаление существующего файла"""
        attr_path = temp_storage_dir / "test.pdf.attr.json"

        # Создание файла
        attrs = FileAttributes(
            file_id=uuid4(),
            original_filename="test.pdf",
            storage_filename="test_user_20250111T120000_abc123.pdf",
            file_size=1024,
            content_type="application/pdf",
            created_at=datetime.now(),
            updated_at=datetime.now(),
            created_by_id="user123",
            created_by_username="testuser",
            storage_path="2025/01/11/12/test.pdf",
            checksum="a" * 64
        )

        await write_attr_file(attr_path, attrs)
        assert attr_path.exists()

        # Удаление файла
        await delete_attr_file(attr_path)

        assert not attr_path.exists()

    @pytest.mark.asyncio
    async def test_delete_nonexistent_file(self, temp_storage_dir):
        """Удаление несуществующего файла"""
        attr_path = temp_storage_dir / "nonexistent.pdf.attr.json"

        with pytest.raises(FileNotFoundError):
            await delete_attr_file(attr_path)


# ==========================================
# Test get_attr_file_path
# ==========================================

class TestGetAttrFilePath:
    """Тесты для get_attr_file_path()"""

    def test_get_path_basic(self):
        """Базовое получение пути к attr файлу"""
        data_path = Path("/storage/file.pdf")
        attr_path = get_attr_file_path(data_path)

        assert attr_path == Path("/storage/file.pdf.attr.json")

    def test_get_path_with_subdirectories(self):
        """Получение пути с поддиректориями"""
        data_path = Path("/storage/2025/01/11/12/document.pdf")
        attr_path = get_attr_file_path(data_path)

        assert attr_path == Path("/storage/2025/01/11/12/document.pdf.attr.json")

    def test_get_path_no_extension(self):
        """Получение пути для файла без расширения"""
        data_path = Path("/storage/file")
        attr_path = get_attr_file_path(data_path)

        assert attr_path == Path("/storage/file.attr.json")


# ==========================================
# Test verify_attr_file_consistency
# ==========================================

class TestVerifyAttrFileConsistency:
    """Тесты для verify_attr_file_consistency()"""

    @pytest.mark.asyncio
    async def test_verify_consistent_files(self, temp_storage_dir):
        """Проверка консистентных файлов"""
        data_path = temp_storage_dir / "test.pdf"
        attr_path = temp_storage_dir / "test.pdf.attr.json"

        # Создание data файла
        file_content = b"Test PDF content" * 100
        data_path.write_bytes(file_content)

        # Создание attr файла с правильным размером
        attrs = FileAttributes(
            file_id=uuid4(),
            original_filename="test.pdf",
            storage_filename="test_user_20250111T120000_abc123.pdf",
            file_size=len(file_content),  # Правильный размер
            content_type="application/pdf",
            created_at=datetime.now(),
            updated_at=datetime.now(),
            created_by_id="user123",
            created_by_username="testuser",
            storage_path="2025/01/11/12/test.pdf",
            checksum="a" * 64
        )

        await write_attr_file(attr_path, attrs)

        # Проверка консистентности
        result = await verify_attr_file_consistency(data_path, attr_path)

        assert result is True

    @pytest.mark.asyncio
    async def test_verify_size_mismatch(self, temp_storage_dir):
        """Проверка несовпадения размера файла"""
        data_path = temp_storage_dir / "test.pdf"
        attr_path = temp_storage_dir / "test.pdf.attr.json"

        # Создание data файла
        data_path.write_bytes(b"content" * 100)

        # Создание attr файла с неправильным размером
        attrs = FileAttributes(
            file_id=uuid4(),
            original_filename="test.pdf",
            storage_filename="test_user_20250111T120000_abc123.pdf",
            file_size=999999,  # Неправильный размер
            content_type="application/pdf",
            created_at=datetime.now(),
            updated_at=datetime.now(),
            created_by_id="user123",
            created_by_username="testuser",
            storage_path="2025/01/11/12/test.pdf",
            checksum="a" * 64
        )

        await write_attr_file(attr_path, attrs)

        # Проверка консистентности
        result = await verify_attr_file_consistency(data_path, attr_path)

        assert result is False

    @pytest.mark.asyncio
    async def test_verify_missing_data_file(self, temp_storage_dir):
        """Проверка отсутствия data файла"""
        data_path = temp_storage_dir / "nonexistent.pdf"
        attr_path = temp_storage_dir / "nonexistent.pdf.attr.json"

        # Создание только attr файла (без data файла)
        attrs = FileAttributes(
            file_id=uuid4(),
            original_filename="test.pdf",
            storage_filename="test_user_20250111T120000_abc123.pdf",
            file_size=1024,
            content_type="application/pdf",
            created_at=datetime.now(),
            updated_at=datetime.now(),
            created_by_id="user123",
            created_by_username="testuser",
            storage_path="2025/01/11/12/test.pdf",
            checksum="a" * 64
        )

        await write_attr_file(attr_path, attrs)

        # Проверка консистентности
        result = await verify_attr_file_consistency(data_path, attr_path)

        assert result is False

    @pytest.mark.asyncio
    async def test_verify_missing_attr_file(self, temp_storage_dir):
        """Проверка отсутствия attr файла"""
        data_path = temp_storage_dir / "test.pdf"

        # Создание только data файла
        data_path.write_bytes(b"content")

        # Проверка консистентности (attr файл будет вычислен автоматически)
        result = await verify_attr_file_consistency(data_path)

        assert result is False

    @pytest.mark.asyncio
    async def test_verify_auto_detect_attr_path(self, temp_storage_dir):
        """Проверка автоматического вычисления пути к attr файлу"""
        data_path = temp_storage_dir / "test.pdf"

        # Создание data файла
        file_content = b"content" * 100
        data_path.write_bytes(file_content)

        # Создание attr файла (путь будет вычислен автоматически)
        attr_path = get_attr_file_path(data_path)
        attrs = FileAttributes(
            file_id=uuid4(),
            original_filename="test.pdf",
            storage_filename="test_user_20250111T120000_abc123.pdf",
            file_size=len(file_content),
            content_type="application/pdf",
            created_at=datetime.now(),
            updated_at=datetime.now(),
            created_by_id="user123",
            created_by_username="testuser",
            storage_path="2025/01/11/12/test.pdf",
            checksum="a" * 64
        )

        await write_attr_file(attr_path, attrs)

        # Проверка консистентности без явного указания attr_path
        result = await verify_attr_file_consistency(data_path)

        assert result is True


# ==========================================
# Integration Tests
# ==========================================

class TestAttrUtilsIntegration:
    """Интеграционные тесты для attr_utils"""

    @pytest.mark.asyncio
    async def test_write_read_roundtrip(self, temp_storage_dir):
        """Полный цикл: запись → чтение"""
        attr_path = temp_storage_dir / "roundtrip.pdf.attr.json"

        file_id = uuid4()
        created_at = datetime(2025, 1, 11, 12, 30, 45)

        # Запись
        attrs_write = FileAttributes(
            file_id=file_id,
            original_filename="roundtrip.pdf",
            storage_filename="roundtrip_user_20250111T123045_abc123.pdf",
            file_size=2048,
            content_type="application/pdf",
            created_at=created_at,
            updated_at=created_at,
            created_by_id="user123",
            created_by_username="testuser",
            created_by_fullname="Test User",
            description="Test document for roundtrip",
            storage_path="2025/01/11/12/roundtrip.pdf",
            checksum="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
            metadata={"project": "test", "priority": "high"}
        )

        await write_attr_file(attr_path, attrs_write)

        # Чтение
        attrs_read = await read_attr_file(attr_path)

        # Проверка roundtrip
        assert attrs_read.file_id == file_id
        assert attrs_read.original_filename == "roundtrip.pdf"
        assert attrs_read.file_size == 2048
        assert attrs_read.created_by_fullname == "Test User"
        assert attrs_read.description == "Test document for roundtrip"
        assert attrs_read.metadata["project"] == "test"
        assert attrs_read.metadata["priority"] == "high"
