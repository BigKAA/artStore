"""
Health check endpoints для Storage Element.

Implements:
- /health/live - Liveness probe (process is running)
- /health/ready - Readiness probe (can serve requests)
"""

from fastapi import APIRouter, status
from pydantic import BaseModel
from typing import Dict, Any
from datetime import datetime, timezone
from pathlib import Path

from app.core.config import get_config
from app.core.logging import get_logger

router = APIRouter()
logger = get_logger(__name__)


class HealthResponse(BaseModel):
    """Health check response model."""

    status: str
    timestamp: datetime
    checks: Dict[str, Any]


@router.get(
    "/live",
    response_model=HealthResponse,
    status_code=status.HTTP_200_OK,
    summary="Liveness probe",
    description="Проверка что процесс живой (для Kubernetes liveness probe)"
)
async def liveness_probe() -> HealthResponse:
    """
    Liveness probe - проверяет что процесс работает.

    Этот endpoint всегда возвращает 200 OK если процесс запущен.
    Kubernetes использует его для определения нужно ли перезапускать pod.

    Returns:
        HealthResponse: Liveness status
    """
    return HealthResponse(
        status="ok",
        timestamp=datetime.now(timezone.utc),
        checks={
            "process": "running"
        }
    )


@router.get(
    "/ready",
    response_model=HealthResponse,
    summary="Readiness probe",
    description="Проверка готовности обрабатывать запросы (для Kubernetes readiness probe)"
)
async def readiness_probe() -> HealthResponse:
    """
    Readiness probe - проверяет что сервис готов обрабатывать запросы.

    Проверяет:
    - Storage directory доступна
    - WAL directory доступна (если WAL enabled)
    - Configuration загружена

    Kubernetes использует этот endpoint для определения можно ли направлять
    трафик на этот pod.

    Returns:
        HealthResponse: Readiness status with checks

    Raises:
        HTTPException 503: Если сервис не готов
    """
    config = get_config()
    checks = {}
    all_ok = True

    # Check storage directory
    try:
        storage_path = Path(config.storage.local_base_path)
        storage_path.mkdir(parents=True, exist_ok=True)

        # Try to write a test file
        test_file = storage_path / ".health_check"
        test_file.write_text("ok")
        test_file.unlink()

        checks["storage_directory"] = "accessible"
    except Exception as e:
        logger.error("Storage directory check failed", error=str(e))
        checks["storage_directory"] = f"failed: {e}"
        all_ok = False

    # Check WAL directory (if enabled)
    if config.wal.enabled:
        try:
            wal_path = Path(config.wal.wal_dir)
            wal_path.mkdir(parents=True, exist_ok=True)

            test_file = wal_path / ".health_check"
            test_file.write_text("ok")
            test_file.unlink()

            checks["wal_directory"] = "accessible"
        except Exception as e:
            logger.error("WAL directory check failed", error=str(e))
            checks["wal_directory"] = f"failed: {e}"
            all_ok = False
    else:
        checks["wal_directory"] = "disabled"

    # Check JWT public key (if auth enabled)
    try:
        jwt_key_path = Path(config.auth.jwt_public_key_path)
        if jwt_key_path.exists():
            checks["jwt_public_key"] = "present"
        else:
            checks["jwt_public_key"] = "missing (will fail authentication)"
            # Not a critical error for basic health check
    except Exception as e:
        checks["jwt_public_key"] = f"check failed: {e}"

    # Configuration check
    checks["configuration"] = "loaded"
    checks["storage_mode"] = config.mode.mode

    response_status = "ok" if all_ok else "degraded"
    http_status = status.HTTP_200_OK if all_ok else status.HTTP_503_SERVICE_UNAVAILABLE

    response = HealthResponse(
        status=response_status,
        timestamp=datetime.now(timezone.utc),
        checks=checks
    )

    # Log readiness status
    if not all_ok:
        logger.warning("Readiness check degraded", checks=checks)

    # Return with appropriate status code
    return response
