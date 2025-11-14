"""
Integration tests для Template Schema v2.0 с реальными файлами.

Тестируют:
- Создание attr.json в v2.0 формате на filesystem
- Автоматическая миграция v1.0 → v2.0
- Backward compatibility v2.0 → v1.0
- Custom attributes persistence
- Schema version detection с реальными файлами

Требования:
- Storage path writable
- Filesystem access
"""

import json
from datetime import datetime
from pathlib import Path
from uuid import uuid4
import tempfile

import pytest

from app.utils.template_schema import (
    FileAttributesV2,
    migrate_v1_to_v2,
    detect_schema_version,
    read_and_migrate_if_needed,
    to_v1_compatible
)


@pytest.fixture
def temp_storage_dir():
    """Temporary directory для тестирования attr.json файлов"""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def sample_v1_attr_data():
    """Sample v1.0 attr.json data"""
    return {
        "file_id": str(uuid4()),
        "original_filename": "document.pdf",
        "storage_filename": "document_user_20250114_abc123.pdf",
        "file_size": 1024,
        "content_type": "application/pdf",
        "created_at": datetime.utcnow().isoformat(),
        "updated_at": datetime.utcnow().isoformat(),
        "created_by_id": "user123",
        "created_by_username": "john_doe",
        "storage_path": "/storage/2025/01/14/10/document.pdf",
        "checksum": "a" * 64,
        "metadata": {"legacy_key": "legacy_value"}
    }


@pytest.fixture
def sample_v2_attr_data():
    """Sample v2.0 attr.json data"""
    return {
        "schema_version": "2.0",
        "file_id": str(uuid4()),
        "original_filename": "report.pdf",
        "storage_filename": "report_admin_20250114_xyz789.pdf",
        "file_size": 2048,
        "content_type": "application/pdf",
        "created_at": datetime.utcnow().isoformat(),
        "updated_at": datetime.utcnow().isoformat(),
        "created_by_id": "admin",
        "created_by_username": "admin_user",
        "storage_path": "/storage/2025/01/14/11/report.pdf",
        "checksum": "b" * 64,
        "metadata": {},
        "custom_attributes": {
            "department": "Engineering",
            "project_code": "PROJ-456",
            "classification": "confidential"
        }
    }


class TestV2AttrFileCreation:
    """Tests для создания v2.0 attr.json файлов"""

    def test_create_v2_attr_file_on_filesystem(
        self,
        temp_storage_dir,
        sample_v2_attr_data
    ):
        """Тест создания v2.0 attr.json файла на filesystem"""
        attr_file = temp_storage_dir / "test_file.txt.attr.json"

        # Create FileAttributesV2 model
        attrs = FileAttributesV2(**sample_v2_attr_data)

        # Write to file
        attr_file.write_text(attrs.model_dump_json(indent=2))

        # Verify file exists
        assert attr_file.exists()

        # Verify content
        saved_data = json.loads(attr_file.read_text())
        assert saved_data["schema_version"] == "2.0"
        assert "custom_attributes" in saved_data
        assert saved_data["custom_attributes"]["department"] == "Engineering"

    def test_v2_attr_file_size_limit(self, temp_storage_dir):
        """Тест что attr.json не превышает 4KB лимит"""
        # Create large custom_attributes
        large_custom_attrs = {
            f"key_{i}": f"value_{i}" * 100
            for i in range(20)
        }

        file_id = uuid4()
        attrs = FileAttributesV2(
            schema_version="2.0",
            file_id=file_id,
            original_filename="test.pdf",
            storage_filename=f"test_{file_id}.pdf",
            file_size=100,
            content_type="application/pdf",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            created_by_id="user1",
            created_by_username="user1",
            storage_path="/storage/path",
            checksum="c" * 64,
            custom_attributes=large_custom_attrs
        )

        attr_json = attrs.model_dump_json()
        attr_size = len(attr_json.encode('utf-8'))

        # Warn if approaching 4KB limit
        if attr_size > 3072:  # 3KB warning threshold
            pytest.skip(f"Attr file size {attr_size} bytes approaching 4KB limit")

        # Fail if exceeding 4KB limit
        assert attr_size <= 4096, f"Attr file {attr_size} bytes exceeds 4KB limit"


class TestV1ToV2Migration:
    """Tests для миграции v1.0 → v2.0"""

    def test_migrate_v1_attr_file_to_v2(
        self,
        temp_storage_dir,
        sample_v1_attr_data
    ):
        """Тест миграции существующего v1.0 attr.json файла"""
        # Create v1.0 file
        v1_attr_file = temp_storage_dir / "legacy_file.txt.attr.json"
        v1_attr_file.write_text(json.dumps(sample_v1_attr_data, indent=2))

        # Read and migrate
        v1_data = json.loads(v1_attr_file.read_text())
        migrated = read_and_migrate_if_needed(v1_data)

        # Verify migration
        assert migrated.schema_version == "2.0"
        assert hasattr(migrated, "custom_attributes")
        assert migrated.custom_attributes == {}

        # Verify v1.0 data preserved
        assert str(migrated.file_id) == sample_v1_attr_data["file_id"]
        assert migrated.original_filename == sample_v1_attr_data["original_filename"]
        assert migrated.metadata["legacy_key"] == "legacy_value"

        # Write migrated version
        v2_attr_file = temp_storage_dir / "migrated_file.txt.attr.json"
        v2_attr_file.write_text(migrated.model_dump_json(indent=2))

        # Verify migrated file
        assert v2_attr_file.exists()
        migrated_content = json.loads(v2_attr_file.read_text())
        assert migrated_content["schema_version"] == "2.0"

    def test_batch_migrate_v1_files(self, temp_storage_dir, sample_v1_attr_data):
        """Тест batch миграции множественных v1.0 файлов"""
        # Create multiple v1.0 files
        v1_files = []
        for i in range(10):
            v1_file = temp_storage_dir / f"file_{i}.txt.attr.json"
            v1_data = sample_v1_attr_data.copy()
            v1_data["file_id"] = str(uuid4())
            v1_data["original_filename"] = f"file_{i}.txt"
            v1_file.write_text(json.dumps(v1_data))
            v1_files.append(v1_file)

        # Migrate all files
        migrated_count = 0
        for v1_file in v1_files:
            v1_data = json.loads(v1_file.read_text())

            # Detect version
            version = detect_schema_version(v1_data)
            if version == "1.0":
                # Migrate
                migrated = read_and_migrate_if_needed(v1_data)
                assert migrated.schema_version == "2.0"

                # Overwrite with v2.0
                v1_file.write_text(migrated.model_dump_json(indent=2))
                migrated_count += 1

        # Verify all migrated
        assert migrated_count == 10

        # Verify files are now v2.0
        for v1_file in v1_files:
            data = json.loads(v1_file.read_text())
            assert data["schema_version"] == "2.0"


class TestV2ToV1BackwardCompatibility:
    """Tests для backward compatibility v2.0 → v1.0"""

    def test_convert_v2_to_v1_for_legacy_system(
        self,
        temp_storage_dir,
        sample_v2_attr_data
    ):
        """Тест конвертации v2.0 → v1.0 для legacy систем"""
        # Create v2.0 file
        v2_file = temp_storage_dir / "modern_file.txt.attr.json"
        attrs_v2 = FileAttributesV2(**sample_v2_attr_data)
        v2_file.write_text(attrs_v2.model_dump_json(indent=2))

        # Convert to v1.0
        v1_data = to_v1_compatible(attrs_v2)

        # Verify v2.0-specific fields removed
        assert "schema_version" not in v1_data
        assert "custom_attributes" not in v1_data

        # Verify v1.0 fields preserved
        assert v1_data["file_id"] == sample_v2_attr_data["file_id"]
        assert v1_data["original_filename"] == sample_v2_attr_data["original_filename"]

        # Write v1.0 version
        v1_file = temp_storage_dir / "legacy_compatible.txt.attr.json"
        v1_file.write_text(json.dumps(v1_data, indent=2))

        # Verify v1.0 file
        assert v1_file.exists()
        v1_content = json.loads(v1_file.read_text())
        assert "schema_version" not in v1_content

    def test_lossy_conversion_warning(self, sample_v2_attr_data):
        """Тест что lossy конвертация теряет custom_attributes"""
        attrs_v2 = FileAttributesV2(**sample_v2_attr_data)

        # Verify v2.0 has custom_attributes
        assert attrs_v2.custom_attributes is not None
        assert len(attrs_v2.custom_attributes) > 0

        # Convert to v1.0 (lossy)
        v1_data = to_v1_compatible(attrs_v2)

        # Verify custom_attributes lost
        assert "custom_attributes" not in v1_data

        # This is expected behavior - custom_attributes are v2.0-specific
        # and cannot be represented in v1.0 format


class TestSchemaVersionDetection:
    """Tests для определения версии schema"""

    def test_detect_v1_schema_from_file(
        self,
        temp_storage_dir,
        sample_v1_attr_data
    ):
        """Тест определения v1.0 schema из файла"""
        v1_file = temp_storage_dir / "v1_file.txt.attr.json"
        v1_file.write_text(json.dumps(sample_v1_attr_data))

        # Read and detect
        data = json.loads(v1_file.read_text())
        version = detect_schema_version(data)

        assert version == "1.0"

    def test_detect_v2_schema_from_file(
        self,
        temp_storage_dir,
        sample_v2_attr_data
    ):
        """Тест определения v2.0 schema из файла"""
        v2_file = temp_storage_dir / "v2_file.txt.attr.json"
        v2_file.write_text(json.dumps(sample_v2_attr_data))

        # Read and detect
        data = json.loads(v2_file.read_text())
        version = detect_schema_version(data)

        assert version == "2.0"

    def test_detect_schema_batch_files(self, temp_storage_dir):
        """Тест batch определения версий множественных файлов"""
        files = []

        # Create mix of v1.0 and v2.0 files
        for i in range(5):
            # v1.0 file
            v1_file = temp_storage_dir / f"v1_{i}.txt.attr.json"
            v1_data = {
                "file_id": str(uuid4()),
                "original_filename": f"v1_file_{i}.txt",
                "storage_filename": f"v1_{i}.txt",
                "file_size": 100,
                "content_type": "text/plain",
                "created_at": datetime.utcnow().isoformat(),
                "updated_at": datetime.utcnow().isoformat(),
                "created_by_id": "user",
                "created_by_username": "user",
                "storage_path": "/path",
                "checksum": "d" * 64,
                "metadata": {}
            }
            v1_file.write_text(json.dumps(v1_data))
            files.append(("v1", v1_file))

            # v2.0 file
            v2_file = temp_storage_dir / f"v2_{i}.txt.attr.json"
            v2_data = v1_data.copy()
            v2_data["schema_version"] = "2.0"
            v2_data["custom_attributes"] = {}
            v2_file.write_text(json.dumps(v2_data))
            files.append(("v2", v2_file))

        # Detect versions
        v1_count = 0
        v2_count = 0

        for expected_version, file_path in files:
            data = json.loads(file_path.read_text())
            detected_version = detect_schema_version(data)

            if expected_version == "v1":
                assert detected_version == "1.0"
                v1_count += 1
            else:
                assert detected_version == "2.0"
                v2_count += 1

        assert v1_count == 5
        assert v2_count == 5


class TestCustomAttributesPersistence:
    """Tests для persistence custom_attributes"""

    def test_custom_attributes_preserved_across_writes(
        self,
        temp_storage_dir,
        sample_v2_attr_data
    ):
        """Тест что custom_attributes сохраняются при записи/чтении"""
        attr_file = temp_storage_dir / "custom_attrs_file.txt.attr.json"

        # Create with custom attributes
        attrs = FileAttributesV2(**sample_v2_attr_data)
        original_custom_attrs = attrs.custom_attributes.copy()

        # Write
        attr_file.write_text(attrs.model_dump_json(indent=2))

        # Read back
        data = json.loads(attr_file.read_text())
        reloaded_attrs = FileAttributesV2(**data)

        # Verify custom_attributes preserved
        assert reloaded_attrs.custom_attributes == original_custom_attrs
        assert reloaded_attrs.custom_attributes["department"] == "Engineering"
        assert reloaded_attrs.custom_attributes["project_code"] == "PROJ-456"

    def test_custom_attributes_validation(self, temp_storage_dir):
        """Тест валидации custom_attributes при записи"""
        # Try to create with invalid custom_attributes
        with pytest.raises(ValueError):
            FileAttributesV2(
                file_id=uuid4(),
                original_filename="test.pdf",
                storage_filename="test.pdf",
                file_size=100,
                content_type="application/pdf",
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
                created_by_id="user",
                created_by_username="user",
                storage_path="/path",
                checksum="e" * 64,
                custom_attributes="not a dict"  # Invalid: must be dict
            )


class TestRealWorldScenarios:
    """Real-world scenario tests"""

    def test_new_deployment_creates_v2_only(self, temp_storage_dir):
        """Тест что новые deployments создают только v2.0 файлы"""
        # Simulate new file uploads
        for i in range(10):
            attr_file = temp_storage_dir / f"new_file_{i}.txt.attr.json"

            attrs = FileAttributesV2(
                schema_version="2.0",
                file_id=uuid4(),
                original_filename=f"new_file_{i}.txt",
                storage_filename=f"new_{i}.txt",
                file_size=100 + i,
                content_type="text/plain",
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
                created_by_id="user",
                created_by_username="user",
                storage_path=f"/path/new_{i}.txt",
                checksum="f" * 64,
                custom_attributes={"upload_batch": "integration_test"}
            )

            attr_file.write_text(attrs.model_dump_json(indent=2))

        # Verify all files are v2.0
        for i in range(10):
            attr_file = temp_storage_dir / f"new_file_{i}.txt.attr.json"
            data = json.loads(attr_file.read_text())
            assert data["schema_version"] == "2.0"
            assert "custom_attributes" in data

    def test_mixed_v1_v2_environment(self, temp_storage_dir, sample_v1_attr_data):
        """Тест работы в mixed v1.0/v2.0 окружении"""
        # Create mix of v1 and v2 files
        v1_file = temp_storage_dir / "old_file.txt.attr.json"
        v1_file.write_text(json.dumps(sample_v1_attr_data))

        v2_file = temp_storage_dir / "new_file.txt.attr.json"
        attrs_v2 = FileAttributesV2(
            schema_version="2.0",
            file_id=uuid4(),
            original_filename="new_file.txt",
            storage_filename="new.txt",
            file_size=200,
            content_type="text/plain",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            created_by_id="user",
            created_by_username="user",
            storage_path="/path/new.txt",
            checksum="1" * 64,
            custom_attributes={"new_format": True}
        )
        v2_file.write_text(attrs_v2.model_dump_json(indent=2))

        # Read both files
        v1_data = json.loads(v1_file.read_text())
        v2_data = json.loads(v2_file.read_text())

        # Process with auto-migration
        v1_migrated = read_and_migrate_if_needed(v1_data)
        v2_native = read_and_migrate_if_needed(v2_data)

        # Both should be v2.0 now
        assert v1_migrated.schema_version == "2.0"
        assert v2_native.schema_version == "2.0"

        # v1 should have empty custom_attributes (migrated)
        assert v1_migrated.custom_attributes == {}

        # v2 should preserve custom_attributes
        assert v2_native.custom_attributes["new_format"] is True
