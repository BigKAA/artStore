"""
Unit tests для file upload API endpoint и service.

Тестирует загрузку файлов с streaming, WAL integration, и validation.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from pathlib import Path
import tempfile
import shutil
from io import BytesIO
from datetime import datetime, timezone

from app.main import app
from app.db.base import Base
from app.api.deps.database import get_db
from app.models import FileMetadata, WAL
from app.core.config import get_config


# Test database setup
@pytest.fixture
def test_db():
    """Create in-memory test database."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine)

    db = SessionLocal()
    yield db

    db.close()
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def test_storage_dir():
    """Create temporary storage directory."""
    temp_dir = Path(tempfile.mkdtemp())
    yield temp_dir
    # Cleanup
    shutil.rmtree(temp_dir)


@pytest.fixture
def client(test_db, test_storage_dir, monkeypatch):
    """Create FastAPI test client with overrides."""
    # Create an engine and session bound to it
    engine = test_db.bind

    # Override database dependency
    def override_get_db():
        SessionLocal = sessionmaker(bind=engine)
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db

    # Override storage path in config
    config = get_config()
    monkeypatch.setattr(config.storage, "local_base_path", str(test_storage_dir))

    with TestClient(app) as c:
        yield c

    app.dependency_overrides.clear()


class TestFileUploadAPI:
    """Тесты для file upload API endpoint."""

    def test_upload_file_success(self, client, test_storage_dir):
        """Тест успешной загрузки файла."""
        # Create test file
        file_content = b"Test file content for upload"
        file_data = BytesIO(file_content)

        # Upload request
        response = client.post(
            "/api/v1/files/upload",
            files={"file": ("test.txt", file_data, "text/plain")},
            data={
                "uploaded_by": "testuser",
                "uploader_full_name": "Test User",
                "description": "Test file upload",
                "retention_days": 365,
                "tags": "test,upload"
            }
        )

        assert response.status_code == 201
        data = response.json()

        # Verify response structure
        assert "file_id" in data
        assert data["original_filename"] == "test.txt"
        assert data["file_size"] == len(file_content)
        assert data["uploaded_by"] == "testuser"
        assert data["retention_days"] == 365
        assert data["tags"] == ["test", "upload"]

        # Verify file exists on disk
        storage_filename = data["storage_filename"]
        storage_path = data["storage_path"]
        file_path = test_storage_dir / storage_path / storage_filename
        assert file_path.exists()

        # Verify attr.json exists
        attr_path = test_storage_dir / storage_path / f"{storage_filename}.attr.json"
        assert attr_path.exists()

    def test_upload_file_no_uploaded_by(self, client):
        """Тест загрузки без указания uploaded_by."""
        file_data = BytesIO(b"test content")

        response = client.post(
            "/api/v1/files/upload",
            files={"file": ("test.txt", file_data, "text/plain")},
            data={"retention_days": 365}
        )

        # Should fail validation
        assert response.status_code == 422  # Unprocessable Entity

    def test_upload_file_invalid_retention(self, client):
        """Тест загрузки с невалидным retention_days."""
        file_data = BytesIO(b"test content")

        response = client.post(
            "/api/v1/files/upload",
            files={"file": ("test.txt", file_data, "text/plain")},
            data={
                "uploaded_by": "testuser",
                "retention_days": -1  # Invalid
            }
        )

        assert response.status_code == 400
        assert "retention_days must be positive" in response.json()["detail"]

    def test_upload_file_invalid_username(self, client):
        """Тест загрузки с невалидным username."""
        file_data = BytesIO(b"test content")

        response = client.post(
            "/api/v1/files/upload",
            files={"file": ("test.txt", file_data, "text/plain")},
            data={
                "uploaded_by": "invalid user!",  # Contains space and special char
                "retention_days": 365
            }
        )

        assert response.status_code == 400
        assert "ASCII alphanumeric" in response.json()["detail"]

    def test_upload_large_file(self, client, test_storage_dir):
        """Тест загрузки большого файла с streaming."""
        # Create 1MB file
        file_content = b"A" * (1024 * 1024)
        file_data = BytesIO(file_content)

        response = client.post(
            "/api/v1/files/upload",
            files={"file": ("large.bin", file_data, "application/octet-stream")},
            data={
                "uploaded_by": "testuser",
                "retention_days": 30
            }
        )

        assert response.status_code == 201
        data = response.json()
        assert data["file_size"] == len(file_content)

        # Verify file on disk
        storage_path = test_storage_dir / data["storage_path"] / data["storage_filename"]
        assert storage_path.exists()
        assert storage_path.stat().st_size == len(file_content)

    def test_upload_with_tags(self, client):
        """Тест загрузки с tags."""
        file_data = BytesIO(b"test content")

        response = client.post(
            "/api/v1/files/upload",
            files={"file": ("test.txt", file_data, "text/plain")},
            data={
                "uploaded_by": "testuser",
                "retention_days": 365,
                "tags": "финансы,квартальный,2025"
            }
        )

        assert response.status_code == 201
        data = response.json()
        assert data["tags"] == ["финансы", "квартальный", "2025"]

    def test_upload_unicode_filename(self, client, test_storage_dir):
        """Тест загрузки файла с Unicode именем."""
        file_data = BytesIO(b"test content")

        response = client.post(
            "/api/v1/files/upload",
            files={"file": ("отчет_2025.pdf", file_data, "application/pdf")},
            data={
                "uploaded_by": "testuser",
                "retention_days": 365
            }
        )

        assert response.status_code == 201
        data = response.json()
        assert data["original_filename"] == "отчет_2025.pdf"

        # Storage filename should be truncated/safe
        assert "testuser" in data["storage_filename"]

    def test_get_file_metadata(self, client, test_db):
        """Тест получения metadata файла по file_id."""
        # First upload a file
        file_data = BytesIO(b"test content")
        upload_response = client.post(
            "/api/v1/files/upload",
            files={"file": ("test.txt", file_data, "text/plain")},
            data={
                "uploaded_by": "testuser",
                "retention_days": 365
            }
        )

        file_id = upload_response.json()["file_id"]

        # Get metadata
        response = client.get(f"/api/v1/files/{file_id}")

        assert response.status_code == 200
        data = response.json()
        assert data["file_id"] == file_id
        assert data["original_filename"] == "test.txt"

    def test_get_nonexistent_file(self, client):
        """Тест получения metadata несуществующего файла."""
        import uuid
        fake_id = str(uuid.uuid4())

        response = client.get(f"/api/v1/files/{fake_id}")

        assert response.status_code == 404
        assert "not found" in response.json()["detail"]

    def test_list_files(self, client):
        """Тест listing файлов."""
        # Upload several files
        for i in range(3):
            file_data = BytesIO(f"test content {i}".encode())
            client.post(
                "/api/v1/files/upload",
                files={"file": (f"test{i}.txt", file_data, "text/plain")},
                data={
                    "uploaded_by": "testuser",
                    "retention_days": 365
                }
            )

        # List files
        response = client.get("/api/v1/files/")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 3
        assert len(data["files"]) == 3

    def test_list_files_filter_by_uploader(self, client):
        """Тест filtering файлов по uploader."""
        # Upload files from different users
        for username in ["user1", "user2", "user1"]:
            file_data = BytesIO(b"test content")
            client.post(
                "/api/v1/files/upload",
                files={"file": (f"test_{username}.txt", file_data, "text/plain")},
                data={
                    "uploaded_by": username,
                    "retention_days": 365
                }
            )

        # Filter by user1
        response = client.get("/api/v1/files/?uploaded_by=user1")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2
        assert all(f["uploaded_by"] == "user1" for f in data["files"])

    def test_list_files_pagination(self, client):
        """Тест pagination при listing файлов."""
        # Upload 5 files
        for i in range(5):
            file_data = BytesIO(f"test {i}".encode())
            client.post(
                "/api/v1/files/upload",
                files={"file": (f"test{i}.txt", file_data, "text/plain")},
                data={
                    "uploaded_by": "testuser",
                    "retention_days": 365
                }
            )

        # Get first page (limit=2)
        response = client.get("/api/v1/files/?limit=2&offset=0")
        data = response.json()
        assert len(data["files"]) == 2
        assert data["total"] == 5

        # Get second page
        response = client.get("/api/v1/files/?limit=2&offset=2")
        data = response.json()
        assert len(data["files"]) == 2


class TestFileUploadService:
    """Тесты для FileUploadService business logic."""

    def test_sha256_calculation(self, client, test_storage_dir):
        """Тест вычисления SHA256 при загрузке."""
        import hashlib

        file_content = b"Test content for SHA256"
        expected_hash = hashlib.sha256(file_content).hexdigest()

        file_data = BytesIO(file_content)
        response = client.post(
            "/api/v1/files/upload",
            files={"file": ("test.txt", file_data, "text/plain")},
            data={
                "uploaded_by": "testuser",
                "retention_days": 365
            }
        )

        assert response.status_code == 201
        data = response.json()
        assert data["sha256"] == expected_hash

    def test_storage_path_hierarchy(self, client, test_storage_dir):
        """Тест иерархической структуры storage path (YYYY/MM/DD/HH)."""
        file_data = BytesIO(b"test content")
        response = client.post(
            "/api/v1/files/upload",
            files={"file": ("test.txt", file_data, "text/plain")},
            data={
                "uploaded_by": "testuser",
                "retention_days": 365
            }
        )

        data = response.json()
        storage_path = data["storage_path"]

        # Should match YYYY/MM/DD/HH pattern
        parts = storage_path.split("/")
        assert len(parts) == 4
        assert len(parts[0]) == 4  # Year
        assert len(parts[1]) == 2  # Month
        assert len(parts[2]) == 2  # Day
        assert len(parts[3]) == 2  # Hour

    def test_retention_expiration_calculation(self, client):
        """Тест расчета retention_expires_at."""
        from datetime import timedelta

        file_data = BytesIO(b"test content")
        response = client.post(
            "/api/v1/files/upload",
            files={"file": ("test.txt", file_data, "text/plain")},
            data={
                "uploaded_by": "testuser",
                "retention_days": 30
            }
        )

        data = response.json()
        uploaded_at = datetime.fromisoformat(data["uploaded_at"])
        expires_at = datetime.fromisoformat(data["retention_expires_at"])

        # Should be 30 days from upload
        delta = expires_at - uploaded_at
        assert abs(delta.days - 30) <= 1  # Allow 1 day tolerance
