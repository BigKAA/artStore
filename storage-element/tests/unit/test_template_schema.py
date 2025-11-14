"""
Unit tests для Template Schema v2.0.

Тестируемые функции:
- FileAttributesV2 validation
- migrate_v1_to_v2() - миграция v1.0 → v2.0
- detect_schema_version() - определение версии
- read_and_migrate_if_needed() - auto-migration при чтении
- to_v1_compatible() - конвертация v2.0 → v1.0 (lossy)

Сценарии:
- Создание v2.0 attributes с валидацией
- Миграция v1.0 → v2.0
- Автоматическая миграция при чтении v1.0 файлов
- Custom attributes validation
- Schema version detection
- Backward compatibility (v2.0 → v1.0)
"""

import json
import pytest
from datetime import datetime
from uuid import uuid4

from app.utils.template_schema import (
    FileAttributesV2,
    CURRENT_SCHEMA_VERSION,
    migrate_v1_to_v2,
    detect_schema_version,
    read_and_migrate_if_needed,
    to_v1_compatible
)
from app.core.exceptions import InvalidAttributeFileException


class TestFileAttributesV2Model:
    """Тесты для FileAttributesV2 Pydantic model"""

    def test_create_v2_attributes_with_all_fields(self):
        """Тест создания v2.0 attributes со всеми полями"""
        file_id = uuid4()
        now = datetime.utcnow()

        attrs = FileAttributesV2(
            schema_version="2.0",
            file_id=file_id,
            original_filename="report.pdf",
            storage_filename="report_user_20250113_abc123.pdf",
            file_size=1024,
            content_type="application/pdf",
            created_at=now,
            updated_at=now,
            created_by_id="user123",
            created_by_username="john_doe",
            created_by_fullname="John Doe",
            description="Annual Report 2024",
            version="1.0",
            storage_path="2025/01/13/10/report_user_20250113_abc123.pdf",
            checksum="a" * 64,  # Valid SHA256
            metadata={"legacy_key": "legacy_value"},
            custom_attributes={
                "department": "Engineering",
                "project_code": "PROJ-123",
                "classification": "internal"
            }
        )

        assert attrs.schema_version == "2.0"
        assert attrs.file_id == file_id
        assert attrs.custom_attributes["department"] == "Engineering"
        assert attrs.metadata["legacy_key"] == "legacy_value"

    def test_create_v2_attributes_minimal_fields(self):
        """Тест создания v2.0 с минимальными обязательными полями"""
        file_id = uuid4()
        now = datetime.utcnow()

        attrs = FileAttributesV2(
            file_id=file_id,
            original_filename="file.txt",
            storage_filename="file_user_20250113_xyz.txt",
            file_size=100,
            content_type="text/plain",
            created_at=now,
            updated_at=now,
            created_by_id="user1",
            created_by_username="user1",
            storage_path="2025/01/13/10/file.txt",
            checksum="b" * 64
        )

        # schema_version должен быть по умолчанию "2.0"
        assert attrs.schema_version == CURRENT_SCHEMA_VERSION
        # custom_attributes должен быть пустым dict
        assert attrs.custom_attributes == {}
        # metadata должен быть пустым dict
        assert attrs.metadata == {}

    def test_custom_attributes_validation(self):
        """Тест валидации custom_attributes"""
        file_id = uuid4()
        now = datetime.utcnow()

        # Valid custom_attributes
        attrs = FileAttributesV2(
            file_id=file_id,
            original_filename="test.pdf",
            storage_filename="test.pdf",
            file_size=100,
            content_type="application/pdf",
            created_at=now,
            updated_at=now,
            created_by_id="user1",
            created_by_username="user1",
            storage_path="path",
            checksum="c" * 64,
            custom_attributes={
                "string_field": "value",
                "number_field": 42,
                "bool_field": True,
                "array_field": [1, 2, 3],
                "nested_field": {"key": "value"}
            }
        )

        assert attrs.custom_attributes["string_field"] == "value"
        assert attrs.custom_attributes["number_field"] == 42

    def test_invalid_checksum_validation(self):
        """Тест валидации invalid checksum"""
        with pytest.raises(ValueError, match="Checksum must be 64 characters"):
            FileAttributesV2(
                file_id=uuid4(),
                original_filename="test.pdf",
                storage_filename="test.pdf",
                file_size=100,
                content_type="application/pdf",
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
                created_by_id="user1",
                created_by_username="user1",
                storage_path="path",
                checksum="invalid"  # Слишком короткий
            )

    def test_invalid_file_size_validation(self):
        """Тест валидации invalid file_size"""
        with pytest.raises(ValueError, match="Input should be greater than 0"):
            FileAttributesV2(
                file_id=uuid4(),
                original_filename="test.pdf",
                storage_filename="test.pdf",
                file_size=0,  # Invalid: должен быть > 0
                content_type="application/pdf",
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
                created_by_id="user1",
                created_by_username="user1",
                storage_path="path",
                checksum="d" * 64
            )

    def test_unsupported_schema_version(self):
        """Тест валидации unsupported schema version"""
        with pytest.raises(ValueError, match="Unsupported schema version"):
            FileAttributesV2(
                schema_version="3.0",  # Unsupported
                file_id=uuid4(),
                original_filename="test.pdf",
                storage_filename="test.pdf",
                file_size=100,
                content_type="application/pdf",
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
                created_by_id="user1",
                created_by_username="user1",
                storage_path="path",
                checksum="e" * 64
            )


class TestMigrationV1ToV2:
    """Тесты для migrate_v1_to_v2()"""

    def test_migrate_v1_to_v2_adds_schema_version(self):
        """Тест что миграция добавляет schema_version"""
        v1_data = {
            "file_id": str(uuid4()),
            "original_filename": "report.pdf",
            "storage_filename": "report_user_timestamp_uuid.pdf",
            "file_size": 1024,
            "content_type": "application/pdf",
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
            "created_by_id": "user1",
            "created_by_username": "john_doe",
            "storage_path": "2025/01/13/report.pdf",
            "checksum": "f" * 64,
            "metadata": {}
        }

        v2_data = migrate_v1_to_v2(v1_data)

        assert v2_data["schema_version"] == CURRENT_SCHEMA_VERSION
        assert "custom_attributes" in v2_data
        assert v2_data["custom_attributes"] == {}

    def test_migrate_preserves_all_v1_fields(self):
        """Тест что миграция сохраняет все поля из v1.0"""
        v1_data = {
            "file_id": str(uuid4()),
            "original_filename": "test.pdf",
            "storage_filename": "test.pdf",
            "file_size": 100,
            "content_type": "application/pdf",
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
            "created_by_id": "user1",
            "created_by_username": "user1",
            "created_by_fullname": "User One",
            "description": "Test document",
            "version": "1.0",
            "storage_path": "path",
            "checksum": "1" * 64,
            "metadata": {"key": "value"}
        }

        v2_data = migrate_v1_to_v2(v1_data)

        # Проверка что все v1 поля сохранены
        for key in v1_data:
            assert v2_data[key] == v1_data[key]

        # Проверка что добавлены новые поля
        assert v2_data["schema_version"] == "2.0"
        assert "custom_attributes" in v2_data


class TestSchemaVersionDetection:
    """Тесты для detect_schema_version()"""

    def test_detect_v2_schema(self):
        """Тест определения v2.0 schema"""
        data = {"schema_version": "2.0", "file_id": str(uuid4())}
        version = detect_schema_version(data)
        assert version == "2.0"

    def test_detect_v1_schema_no_version_field(self):
        """Тест определения v1.0 (отсутствует schema_version)"""
        data = {"file_id": str(uuid4()), "original_filename": "file.pdf"}
        version = detect_schema_version(data)
        assert version == "1.0"


class TestReadAndMigrateIfNeeded:
    """Тесты для read_and_migrate_if_needed()"""

    def test_read_v2_file_native(self):
        """Тест чтения native v2.0 файла без миграции"""
        now = datetime.utcnow()
        data = {
            "schema_version": "2.0",
            "file_id": str(uuid4()),
            "original_filename": "test.pdf",
            "storage_filename": "test.pdf",
            "file_size": 100,
            "content_type": "application/pdf",
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
            "created_by_id": "user1",
            "created_by_username": "user1",
            "storage_path": "path",
            "checksum": "2" * 64,
            "metadata": {},
            "custom_attributes": {"department": "IT"}
        }

        attrs = read_and_migrate_if_needed(data)

        assert attrs.schema_version == "2.0"
        assert attrs.custom_attributes["department"] == "IT"

    def test_read_v1_file_with_auto_migration(self):
        """Тест чтения v1.0 файла с автоматической миграцией"""
        now = datetime.utcnow()
        v1_data = {
            # НЕТ schema_version - это v1.0
            "file_id": str(uuid4()),
            "original_filename": "legacy.pdf",
            "storage_filename": "legacy.pdf",
            "file_size": 200,
            "content_type": "application/pdf",
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
            "created_by_id": "user2",
            "created_by_username": "user2",
            "storage_path": "path",
            "checksum": "3" * 64,
            "metadata": {"legacy": "data"}
        }

        attrs = read_and_migrate_if_needed(v1_data)

        # Проверка что произошла миграция
        assert attrs.schema_version == "2.0"
        # Проверка что custom_attributes инициализирован
        assert attrs.custom_attributes == {}
        # Проверка что старые поля сохранены
        assert attrs.metadata["legacy"] == "data"

    def test_read_unsupported_schema_version(self):
        """Тест ошибки при unsupported schema version"""
        data = {
            "schema_version": "999.0",  # Unsupported
            "file_id": str(uuid4()),
            "original_filename": "test.pdf"
        }

        with pytest.raises(InvalidAttributeFileException):
            read_and_migrate_if_needed(data)


class TestBackwardCompatibilityV2ToV1:
    """Тесты для to_v1_compatible()"""

    def test_convert_v2_to_v1_removes_new_fields(self):
        """Тест что конвертация v2→v1 удаляет новые поля"""
        now = datetime.utcnow()
        v2_attrs = FileAttributesV2(
            schema_version="2.0",
            file_id=uuid4(),
            original_filename="test.pdf",
            storage_filename="test.pdf",
            file_size=100,
            content_type="application/pdf",
            created_at=now,
            updated_at=now,
            created_by_id="user1",
            created_by_username="user1",
            storage_path="path",
            checksum="4" * 64,
            metadata={"legacy": "value"},
            custom_attributes={"department": "IT"}  # Будет потерян!
        )

        v1_data = to_v1_compatible(v2_attrs)

        # Проверка что v2.0-specific поля удалены
        assert "schema_version" not in v1_data
        assert "custom_attributes" not in v1_data

        # Проверка что v1.0 поля сохранены
        assert v1_data["file_id"] == str(v2_attrs.file_id)
        assert v1_data["original_filename"] == "test.pdf"
        assert v1_data["metadata"]["legacy"] == "value"

    def test_convert_v2_to_v1_is_lossy(self):
        """Тест что конвертация v2→v1 lossy (custom_attributes теряются)"""
        now = datetime.utcnow()
        v2_attrs = FileAttributesV2(
            schema_version="2.0",
            file_id=uuid4(),
            original_filename="doc.pdf",
            storage_filename="doc.pdf",
            file_size=500,
            content_type="application/pdf",
            created_at=now,
            updated_at=now,
            created_by_id="user3",
            created_by_username="user3",
            storage_path="path",
            checksum="5" * 64,
            custom_attributes={
                "department": "Engineering",
                "project_code": "PROJ-456",
                "classification": "confidential"
            }
        )

        v1_data = to_v1_compatible(v2_attrs)

        # Проверка что custom_attributes потерян
        assert "custom_attributes" not in v1_data
        # Предупреждение должно быть залогировано (проверяется через logs)


class TestJSONSerializationV2:
    """Тесты для JSON serialization/deserialization v2.0"""

    def test_serialize_v2_to_json(self):
        """Тест сериализации v2.0 в JSON"""
        now = datetime.utcnow()
        v2_attrs = FileAttributesV2(
            file_id=uuid4(),
            original_filename="report.pdf",
            storage_filename="report.pdf",
            file_size=1024,
            content_type="application/pdf",
            created_at=now,
            updated_at=now,
            created_by_id="user1",
            created_by_username="john_doe",
            storage_path="path",
            checksum="6" * 64,
            custom_attributes={"key": "value"}
        )

        json_str = v2_attrs.model_dump_json()
        data = json.loads(json_str)

        assert data["schema_version"] == "2.0"
        assert data["custom_attributes"]["key"] == "value"
        assert isinstance(data["file_id"], str)
        assert isinstance(data["created_at"], str)

    def test_deserialize_v2_from_json(self):
        """Тест десериализации v2.0 из JSON"""
        json_str = '''
        {
            "schema_version": "2.0",
            "file_id": "550e8400-e29b-41d4-a716-446655440000",
            "original_filename": "test.pdf",
            "storage_filename": "test.pdf",
            "file_size": 100,
            "content_type": "application/pdf",
            "created_at": "2025-01-13T10:00:00",
            "updated_at": "2025-01-13T10:00:00",
            "created_by_id": "user1",
            "created_by_username": "user1",
            "storage_path": "path",
            "checksum": "7777777777777777777777777777777777777777777777777777777777777777",
            "metadata": {},
            "custom_attributes": {"department": "IT"}
        }
        '''

        data = json.loads(json_str)
        attrs = FileAttributesV2(**data)

        assert attrs.schema_version == "2.0"
        assert attrs.custom_attributes["department"] == "IT"
        assert attrs.file_size == 100
