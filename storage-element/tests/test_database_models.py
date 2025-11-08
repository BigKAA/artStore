"""
Unit tests для database models.

Тестирует SQLAlchemy models и database operations.
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from datetime import datetime, timezone, timedelta
import uuid

from app.db.base import Base
from app.models import FileMetadata, WAL, Config, ConfigKeys
from app.core.atomic_write import OperationType, OperationStatus


@pytest.fixture
def db_engine():
    """Create in-memory SQLite database for testing."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def db_session(db_engine):
    """Create database session for testing."""
    SessionLocal = sessionmaker(bind=db_engine)
    session = SessionLocal()
    yield session
    session.close()


class TestFileMetadata:
    """Тесты для FileMetadata model."""

    def test_create_file_metadata(self, db_session):
        """Тест создания file metadata record."""
        file_id = uuid.uuid4()
        now = datetime.now(timezone.utc)
        retention_expires = now + timedelta(days=365)

        file_meta = FileMetadata(
            file_id=file_id,
            original_filename="report.pdf",
            storage_filename="report_user_20251108T103045_abc123.pdf",
            storage_path="2025/11/08/10",
            file_size=1048576,
            mime_type="application/pdf",
            sha256="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
            uploaded_by="testuser",
            uploader_full_name="Test User",
            description="Test file",
            retention_days=365,
            retention_expires_at=retention_expires
        )

        db_session.add(file_meta)
        db_session.commit()

        # Retrieve and verify
        retrieved = db_session.query(FileMetadata).filter_by(file_id=file_id).first()

        assert retrieved is not None
        assert retrieved.original_filename == "report.pdf"
        assert retrieved.file_size == 1048576
        assert retrieved.uploaded_by == "testuser"
        assert retrieved.version == 1  # Default value

    def test_file_metadata_to_dict(self, db_session):
        """Тест сериализации file metadata в dict."""
        file_meta = FileMetadata(
            original_filename="test.pdf",
            storage_filename="test_user_20251108_abc.pdf",
            storage_path="2025/11/08",
            file_size=1024,
            sha256="abc123",
            uploaded_by="user",
            retention_days=30,
            retention_expires_at=datetime.now(timezone.utc) + timedelta(days=30)
        )

        db_session.add(file_meta)
        db_session.commit()

        data = file_meta.to_dict()

        assert "file_id" in data
        assert data["original_filename"] == "test.pdf"
        assert data["file_size"] == 1024
        assert data["version"] == 1

    def test_file_metadata_with_tags(self, db_session):
        """Тест file metadata с tags array."""
        file_meta = FileMetadata(
            original_filename="document.pdf",
            storage_filename="doc.pdf",
            storage_path="2025/11",
            file_size=2048,
            sha256="def456",
            uploaded_by="admin",
            tags=["финансы", "квартальный", "2025"],
            retention_days=365,
            retention_expires_at=datetime.now(timezone.utc) + timedelta(days=365)
        )

        db_session.add(file_meta)
        db_session.commit()

        retrieved = db_session.query(FileMetadata).first()
        assert retrieved.tags == ["финансы", "квартальный", "2025"]

    def test_file_metadata_unique_storage_filename(self, db_session):
        """Тест уникальности storage_filename."""
        file1 = FileMetadata(
            original_filename="file1.pdf",
            storage_filename="unique_name.pdf",
            storage_path="2025",
            file_size=100,
            sha256="hash1",
            uploaded_by="user",
            retention_days=30,
            retention_expires_at=datetime.now(timezone.utc) + timedelta(days=30)
        )

        db_session.add(file1)
        db_session.commit()

        # Try to create duplicate storage_filename
        file2 = FileMetadata(
            original_filename="file2.pdf",
            storage_filename="unique_name.pdf",  # Same as file1
            storage_path="2025",
            file_size=200,
            sha256="hash2",
            uploaded_by="user",
            retention_days=30,
            retention_expires_at=datetime.now(timezone.utc) + timedelta(days=30)
        )

        db_session.add(file2)

        # SQLite doesn't enforce unique constraints the same way as PostgreSQL
        # In real PostgreSQL this would raise IntegrityError
        with pytest.raises(Exception):  # Generic exception for SQLite
            db_session.commit()


class TestWAL:
    """Тесты для WAL model."""

    def test_create_wal_entry(self, db_session):
        """Тест создания WAL entry."""
        tx_id = uuid.uuid4()

        wal_entry = WAL(
            transaction_id=tx_id,
            operation_type="upload",
            operation_status="pending",
            payload={"file_id": "test123", "size": 1024},
            compensation_data={"action": "delete", "file_id": "test123"}
        )

        db_session.add(wal_entry)
        db_session.commit()

        retrieved = db_session.query(WAL).filter_by(transaction_id=tx_id).first()

        assert retrieved is not None
        assert retrieved.operation_type == "upload"
        assert retrieved.operation_status == "pending"
        assert retrieved.payload["file_id"] == "test123"

    def test_wal_with_saga_id(self, db_session):
        """Тест WAL entry с saga_id."""
        wal_entry = WAL(
            transaction_id=uuid.uuid4(),
            saga_id="saga-upload-12345",
            operation_type="upload",
            operation_status="in_progress",
            payload={}
        )

        db_session.add(wal_entry)
        db_session.commit()

        retrieved = db_session.query(WAL).filter_by(saga_id="saga-upload-12345").first()

        assert retrieved is not None
        assert retrieved.saga_id == "saga-upload-12345"

    def test_wal_status_transition(self, db_session):
        """Тест изменения статуса WAL entry."""
        wal_entry = WAL(
            transaction_id=uuid.uuid4(),
            operation_type="delete",
            operation_status="pending",
            payload={}
        )

        db_session.add(wal_entry)
        db_session.commit()

        # Update status
        wal_entry.operation_status = "committed"
        wal_entry.committed_at = datetime.now(timezone.utc)
        db_session.commit()

        retrieved = db_session.query(WAL).filter_by(wal_id=wal_entry.wal_id).first()

        assert retrieved.operation_status == "committed"
        assert retrieved.committed_at is not None

    def test_wal_to_dict(self, db_session):
        """Тест сериализации WAL в dict."""
        wal_entry = WAL(
            transaction_id=uuid.uuid4(),
            operation_type="update_metadata",
            operation_status="committed",
            payload={"test": "data"}
        )

        db_session.add(wal_entry)
        db_session.commit()

        data = wal_entry.to_dict()

        assert "wal_id" in data
        assert "transaction_id" in data
        assert data["operation_type"] == "update_metadata"
        assert data["payload"] == {"test": "data"}


class TestConfig:
    """Тесты для Config model."""

    def test_create_config_entry(self, db_session):
        """Тест создания config entry."""
        config = Config(
            key="storage_mode",
            value="edit",
            description="Current storage mode"
        )

        db_session.add(config)
        db_session.commit()

        retrieved = db_session.query(Config).filter_by(key="storage_mode").first()

        assert retrieved is not None
        assert retrieved.value == "edit"
        assert retrieved.description == "Current storage mode"

    def test_update_config_value(self, db_session):
        """Тест обновления config value."""
        config = Config(
            key="total_files",
            value="0"
        )

        db_session.add(config)
        db_session.commit()

        # Update value
        config.value = "100"
        db_session.commit()

        retrieved = db_session.query(Config).filter_by(key="total_files").first()
        assert retrieved.value == "100"

    def test_config_keys_constants(self):
        """Тест ConfigKeys constants."""
        assert ConfigKeys.STORAGE_MODE == "storage_mode"
        assert ConfigKeys.MASTER_NODE_ID == "master_node_id"
        assert ConfigKeys.TOTAL_FILES == "total_files"

    def test_config_to_dict(self, db_session):
        """Тест сериализации Config в dict."""
        config = Config(
            key="test_key",
            value="test_value",
            description="Test description"
        )

        db_session.add(config)
        db_session.commit()

        data = config.to_dict()

        assert data["key"] == "test_key"
        assert data["value"] == "test_value"
        assert data["description"] == "Test description"


class TestDatabaseIntegration:
    """Интеграционные тесты для database operations."""

    def test_multiple_files_query(self, db_session):
        """Тест запроса множественных файлов."""
        # Create multiple files
        for i in range(5):
            file_meta = FileMetadata(
                original_filename=f"file{i}.pdf",
                storage_filename=f"file{i}_user_20251108_abc{i}.pdf",
                storage_path="2025/11",
                file_size=1024 * (i + 1),
                sha256=f"hash{i}",
                uploaded_by="testuser",
                retention_days=365,
                retention_expires_at=datetime.now(timezone.utc) + timedelta(days=365)
            )
            db_session.add(file_meta)

        db_session.commit()

        # Query all files
        files = db_session.query(FileMetadata).all()
        assert len(files) == 5

        # Query by uploader
        user_files = db_session.query(FileMetadata).filter_by(uploaded_by="testuser").all()
        assert len(user_files) == 5

    def test_wal_and_file_relationship(self, db_session):
        """Тест связи между WAL и FileMetadata через file_id."""
        file_id = uuid.uuid4()

        # Create file metadata
        file_meta = FileMetadata(
            file_id=file_id,
            original_filename="test.pdf",
            storage_filename="test.pdf",
            storage_path="2025",
            file_size=1024,
            sha256="hash",
            uploaded_by="user",
            retention_days=30,
            retention_expires_at=datetime.now(timezone.utc) + timedelta(days=30)
        )

        # Create WAL entry for this file
        wal_entry = WAL(
            transaction_id=uuid.uuid4(),
            operation_type="upload",
            operation_status="committed",
            file_id=file_id,
            payload={"file_id": str(file_id)}
        )

        db_session.add(file_meta)
        db_session.add(wal_entry)
        db_session.commit()

        # Query WAL entries for this file
        wal_entries = db_session.query(WAL).filter_by(file_id=file_id).all()
        assert len(wal_entries) == 1
        assert wal_entries[0].operation_type == "upload"
