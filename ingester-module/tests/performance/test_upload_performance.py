"""
Performance benchmarks for file upload operations.

Tests:
- Single file upload latency
- Concurrent upload throughput
- File size impact on performance
- Authentication overhead
- Error handling performance
"""

import pytest
import asyncio
from httpx import AsyncClient
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from app.services.upload_service import UploadService
from app.schemas.upload import UploadRequest, StorageMode
from fastapi import UploadFile


@pytest.mark.benchmark
@pytest.mark.asyncio
class TestUploadPerformance:
    """Performance benchmarks for upload operations."""

    async def test_upload_latency_small_file(
        self,
        performance_collector,
        benchmark_timer,
        generate_test_file
    ):
        """
        Benchmark: Single small file upload latency.

        Target: < 50ms for 10KB file
        """
        # Setup
        service = UploadService()
        file_content = generate_test_file(10 * 1024)  # 10KB

        mock_file = MagicMock(spec=UploadFile)
        mock_file.filename = "small_benchmark.txt"
        mock_file.content_type = "text/plain"
        mock_file.read = AsyncMock(return_value=file_content)

        request = UploadRequest(storage_mode=StorageMode.EDIT, compress=False)

        # Mock HTTP response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "id": str(uuid4()),
            "storage_filename": "small_benchmark_testuser_20250114T120000_abc123.txt"
        }

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)

        # Benchmark
        with benchmark_timer() as timer:
            with patch.object(service, '_get_client', return_value=mock_client):
                result = await service.upload_file(
                    file=mock_file,
                    request=request,
                    user_id="benchmark-user",
                    username="benchmark"
                )

        # Record metric
        performance_collector.record("upload_small_file", timer.duration_ms)

        # Assertions
        assert result is not None
        assert timer.duration_ms < 50, f"Upload took {timer.duration_ms}ms, target <50ms"

    async def test_upload_latency_medium_file(
        self,
        performance_collector,
        benchmark_timer,
        generate_test_file
    ):
        """
        Benchmark: Medium file upload latency.

        Target: < 200ms for 1MB file
        """
        service = UploadService()
        file_content = generate_test_file(1 * 1024 * 1024)  # 1MB

        mock_file = MagicMock(spec=UploadFile)
        mock_file.filename = "medium_benchmark.bin"
        mock_file.content_type = "application/octet-stream"
        mock_file.read = AsyncMock(return_value=file_content)

        request = UploadRequest(storage_mode=StorageMode.EDIT, compress=False)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "id": str(uuid4()),
            "storage_filename": "medium_benchmark_testuser_20250114T120000_abc123.bin"
        }

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)

        with benchmark_timer() as timer:
            with patch.object(service, '_get_client', return_value=mock_client):
                result = await service.upload_file(
                    file=mock_file,
                    request=request,
                    user_id="benchmark-user",
                    username="benchmark"
                )

        performance_collector.record("upload_medium_file", timer.duration_ms)

        assert result is not None
        assert timer.duration_ms < 200, f"Upload took {timer.duration_ms}ms, target <200ms"

    async def test_upload_latency_large_file(
        self,
        performance_collector,
        benchmark_timer,
        generate_test_file
    ):
        """
        Benchmark: Large file upload latency.

        Target: < 500ms for 10MB file
        """
        service = UploadService()
        file_content = generate_test_file(10 * 1024 * 1024)  # 10MB

        mock_file = MagicMock(spec=UploadFile)
        mock_file.filename = "large_benchmark.bin"
        mock_file.content_type = "application/octet-stream"
        mock_file.read = AsyncMock(return_value=file_content)

        request = UploadRequest(storage_mode=StorageMode.EDIT, compress=False)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "id": str(uuid4()),
            "storage_filename": "large_benchmark_testuser_20250114T120000_abc123.bin"
        }

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)

        with benchmark_timer() as timer:
            with patch.object(service, '_get_client', return_value=mock_client):
                result = await service.upload_file(
                    file=mock_file,
                    request=request,
                    user_id="benchmark-user",
                    username="benchmark"
                )

        performance_collector.record("upload_large_file", timer.duration_ms)

        assert result is not None
        assert timer.duration_ms < 500, f"Upload took {timer.duration_ms}ms, target <500ms"


@pytest.mark.load_test
@pytest.mark.slow
@pytest.mark.asyncio
class TestUploadThroughput:
    """Load testing scenarios for upload throughput."""

    async def test_concurrent_uploads_10_users(
        self,
        performance_collector,
        load_test_scenario,
        generate_test_file,
        save_performance_report
    ):
        """
        Load Test: 10 concurrent users uploading files.

        Scenario: 100 total uploads, 10 concurrent
        Target: >50 RPS throughput, <200ms avg latency
        """
        service = UploadService()
        file_content = generate_test_file(100 * 1024)  # 100KB

        async def upload_operation(request_id: int):
            """Single upload operation."""
            mock_file = MagicMock(spec=UploadFile)
            mock_file.filename = f"concurrent_test_{request_id}.txt"
            mock_file.content_type = "text/plain"
            mock_file.read = AsyncMock(return_value=file_content)

            request = UploadRequest(storage_mode=StorageMode.EDIT, compress=False)

            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "id": str(uuid4()),
                "storage_filename": f"concurrent_test_{request_id}_user_20250114T120000_abc123.txt"
            }

            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)

            with patch.object(service, '_get_client', return_value=mock_client):
                await service.upload_file(
                    file=mock_file,
                    request=request,
                    user_id=f"user-{request_id}",
                    username=f"user{request_id}"
                )

        # Execute load test
        await load_test_scenario(
            operation=upload_operation,
            concurrent_requests=10,
            total_requests=100,
            collector=performance_collector,
            operation_name="concurrent_upload_10"
        )

        # Generate report
        report = performance_collector.get_report("concurrent_upload_10")

        # Save report
        save_performance_report(report, "concurrent_upload_10.json")

        # Assertions
        assert report.success_rate_pct >= 95, f"Success rate {report.success_rate_pct}% < 95%"
        assert report.throughput_rps >= 50, f"Throughput {report.throughput_rps} RPS < 50 RPS"
        assert report.avg_latency_ms < 200, f"Avg latency {report.avg_latency_ms}ms >= 200ms"

    async def test_concurrent_uploads_50_users(
        self,
        performance_collector,
        load_test_scenario,
        generate_test_file,
        save_performance_report
    ):
        """
        Load Test: 50 concurrent users uploading files.

        Scenario: 500 total uploads, 50 concurrent
        Target: >100 RPS throughput, <500ms avg latency
        """
        service = UploadService()
        file_content = generate_test_file(50 * 1024)  # 50KB

        async def upload_operation(request_id: int):
            mock_file = MagicMock(spec=UploadFile)
            mock_file.filename = f"load_test_{request_id}.txt"
            mock_file.content_type = "text/plain"
            mock_file.read = AsyncMock(return_value=file_content)

            request = UploadRequest(storage_mode=StorageMode.EDIT, compress=False)

            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "id": str(uuid4()),
                "storage_filename": f"load_test_{request_id}_user_20250114T120000_abc123.txt"
            }

            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)

            with patch.object(service, '_get_client', return_value=mock_client):
                await service.upload_file(
                    file=mock_file,
                    request=request,
                    user_id=f"user-{request_id}",
                    username=f"user{request_id}"
                )

        await load_test_scenario(
            operation=upload_operation,
            concurrent_requests=50,
            total_requests=500,
            collector=performance_collector,
            operation_name="concurrent_upload_50"
        )

        report = performance_collector.get_report("concurrent_upload_50")
        save_performance_report(report, "concurrent_upload_50.json")

        assert report.success_rate_pct >= 90, f"Success rate {report.success_rate_pct}% < 90%"
        assert report.throughput_rps >= 100, f"Throughput {report.throughput_rps} RPS < 100 RPS"
        assert report.avg_latency_ms < 500, f"Avg latency {report.avg_latency_ms}ms >= 500ms"


@pytest.mark.benchmark
@pytest.mark.asyncio
class TestUploadAuthenticationOverhead:
    """Performance benchmarks for authentication overhead."""

    async def test_jwt_validation_latency(
        self,
        performance_collector,
        benchmark_timer,
        monkeypatch
    ):
        """
        Benchmark: JWT validation latency.

        Target: < 10ms for JWT validation
        """
        from app.core.security import JWTValidator
        from app.core import config
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.backends import default_backend
        import jwt as pyjwt
        from datetime import datetime, timezone, timedelta
        import tempfile

        # Generate RSA keys
        private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
            backend=default_backend()
        )

        public_key = private_key.public_key()

        public_pem = public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        )

        private_pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption()
        )

        # Create temp key file
        from pathlib import Path
        with tempfile.NamedTemporaryFile(mode='wb', delete=False, suffix='.pem') as f:
            f.write(public_pem)
            public_key_path = Path(f.name)

        # Patch settings to use test key
        monkeypatch.setattr(config.settings.auth, 'public_key_path', public_key_path)

        # Create validator (will load from settings)
        validator = JWTValidator()

        # Generate token
        now = datetime.now(timezone.utc)
        payload = {
            "sub": "benchmark-user",
            "username": "benchmark",
            "role": "USER",
            "type": "access",
            "iat": now,
            "exp": now + timedelta(hours=1)
        }

        token = pyjwt.encode(payload, private_pem, algorithm="RS256")

        # Benchmark validation
        with benchmark_timer() as timer:
            user_context = validator.validate_token(token)

        performance_collector.record("jwt_validation", timer.duration_ms)

        assert user_context is not None
        assert timer.duration_ms < 10, f"JWT validation took {timer.duration_ms}ms, target <10ms"

        # Cleanup
        import os
        os.unlink(public_key_path)
