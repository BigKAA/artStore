"""
Integration tests для Health Endpoints.

Тестирует:
- GET /health/live - Kubernetes liveness probe
- GET /health/ready - Kubernetes readiness probe с проверкой dependencies
- Graceful degradation когда dependencies недоступны

CRITICAL: Эти endpoints обязательны для Kubernetes deployment.
"""

import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from fastapi import status
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    """
    Test client без lifespan для быстрых тестов health endpoints.

    Health endpoints не требуют инициализации БД/Cache,
    поэтому можно пропустить lifespan.
    """
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


class TestLivenessEndpoint:
    """
    Tests для GET /health/live endpoint.

    Liveness probe проверяет что сервер запущен и отвечает.
    ВСЕГДА должен возвращать 200 OK если приложение работает.
    """

    def test_liveness_returns_200_ok(self, client):
        """
        Тест: Liveness probe возвращает 200 OK.

        Kubernetes использует этот endpoint чтобы понять,
        нужно ли перезапустить контейнер.
        """
        response = client.get("/health/live")

        assert response.status_code == status.HTTP_200_OK
        assert response.json() == {"status": "alive"}

    def test_liveness_response_structure(self, client):
        """
        Тест: Liveness response имеет правильную структуру.

        Проверяем что response - это JSON object с полем 'status'.
        """
        response = client.get("/health/live")

        data = response.json()
        assert "status" in data
        assert isinstance(data["status"], str)
        assert data["status"] == "alive"

    def test_liveness_returns_json_content_type(self, client):
        """
        Тест: Liveness возвращает application/json content type.
        """
        response = client.get("/health/live")

        assert response.headers["content-type"] == "application/json"

    def test_liveness_is_fast(self, client):
        """
        Тест: Liveness probe отвечает быстро (<100ms).

        Важно для Kubernetes чтобы probes не создавали latency.
        """
        import time

        start = time.time()
        response = client.get("/health/live")
        elapsed = time.time() - start

        assert response.status_code == status.HTTP_200_OK
        # Liveness должен быть очень быстрым
        assert elapsed < 0.1, f"Liveness too slow: {elapsed:.3f}s"


class TestReadinessEndpoint:
    """
    Tests для GET /health/ready endpoint.

    Readiness probe проверяет что приложение готово принимать трафик.
    Зависит от состояния PostgreSQL и Redis (опционально).
    """

    @pytest.fixture
    def mock_db_healthy(self):
        """Mock для здоровой БД."""
        # Патчим в модуле database где она определена
        with patch("app.db.database.check_db_health", new_callable=AsyncMock) as mock:
            mock.return_value = True
            yield mock

    @pytest.fixture
    def mock_db_unhealthy(self):
        """Mock для недоступной БД."""
        with patch("app.db.database.check_db_health", new_callable=AsyncMock) as mock:
            mock.return_value = False
            yield mock

    @pytest.fixture
    def mock_db_exception(self):
        """Mock для БД с ошибкой подключения."""
        with patch("app.db.database.check_db_health", new_callable=AsyncMock) as mock:
            mock.side_effect = Exception("Database connection refused")
            yield mock

    @pytest.fixture
    def mock_cache_healthy(self):
        """Mock для здорового Redis cache."""
        mock_redis = MagicMock()
        mock_redis.is_available.return_value = True
        # Патчим где используется (в main.py после импорта)
        with patch.object(
            __import__("app.main", fromlist=["cache_service"]),
            "cache_service"
        ) as mock_cache:
            mock_cache.redis_cache = mock_redis
            yield mock_cache

    @pytest.fixture
    def mock_cache_degraded(self):
        """Mock для degraded Redis cache."""
        mock_redis = MagicMock()
        mock_redis.is_available.return_value = False
        with patch.object(
            __import__("app.main", fromlist=["cache_service"]),
            "cache_service"
        ) as mock_cache:
            mock_cache.redis_cache = mock_redis
            yield mock_cache

    @pytest.fixture
    def mock_cache_disabled(self):
        """Mock для отключенного cache."""
        with patch.object(
            __import__("app.main", fromlist=["cache_service"]),
            "cache_service"
        ) as mock_cache:
            mock_cache.redis_cache = None
            yield mock_cache

    def test_readiness_healthy_state(self, client, mock_db_healthy, mock_cache_healthy):
        """
        Тест: Readiness возвращает 'ready' когда DB и Cache здоровы.
        """
        response = client.get("/health/ready")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["status"] == "ready"
        assert data["database"] == "healthy"
        assert data["cache"] == "healthy"

    def test_readiness_db_unhealthy_returns_not_ready(
        self, client, mock_db_unhealthy, mock_cache_healthy
    ):
        """
        Тест: Readiness возвращает 'not_ready' когда DB недоступна.

        БД критична - без неё приложение не может обрабатывать запросы.
        """
        response = client.get("/health/ready")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["status"] == "not_ready"
        assert data["database"] == "unhealthy"

    def test_readiness_db_exception_returns_not_ready(
        self, client, mock_db_exception, mock_cache_healthy
    ):
        """
        Тест: Readiness возвращает 'not_ready' при ошибке подключения к БД.
        """
        response = client.get("/health/ready")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["status"] == "not_ready"
        assert data["database"] == "unhealthy"

    def test_readiness_cache_degraded_still_ready(
        self, client, mock_db_healthy, mock_cache_degraded
    ):
        """
        Тест: Readiness возвращает 'ready' даже при недоступном cache.

        Cache не критичен - приложение может работать без него (медленнее).
        Это graceful degradation.
        """
        response = client.get("/health/ready")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["status"] == "ready"  # Всё равно ready
        assert data["database"] == "healthy"
        assert data["cache"] == "degraded"

    def test_readiness_cache_disabled_still_ready(
        self, client, mock_db_healthy, mock_cache_disabled
    ):
        """
        Тест: Readiness возвращает 'ready' когда cache отключен.
        """
        response = client.get("/health/ready")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["status"] == "ready"
        assert data["database"] == "healthy"
        assert data["cache"] == "disabled"

    def test_readiness_response_structure(self, client, mock_db_healthy, mock_cache_healthy):
        """
        Тест: Readiness response имеет правильную структуру.
        """
        response = client.get("/health/ready")

        data = response.json()
        # Обязательные поля
        assert "status" in data
        assert "database" in data
        assert "cache" in data
        # Типы
        assert isinstance(data["status"], str)
        assert isinstance(data["database"], str)
        assert isinstance(data["cache"], str)
        # Допустимые значения
        assert data["status"] in ["ready", "not_ready"]
        assert data["database"] in ["healthy", "unhealthy", "unknown"]
        assert data["cache"] in ["healthy", "degraded", "disabled", "unknown"]

    def test_readiness_returns_json_content_type(
        self, client, mock_db_healthy, mock_cache_healthy
    ):
        """
        Тест: Readiness возвращает application/json content type.
        """
        response = client.get("/health/ready")

        assert response.headers["content-type"] == "application/json"


class TestHealthEndpointsSecurity:
    """
    Tests для security аспектов health endpoints.

    Health endpoints должны быть доступны без аутентификации,
    но не должны раскрывать чувствительную информацию.
    """

    def test_liveness_no_auth_required(self, client):
        """
        Тест: Liveness доступен без Authorization header.

        Kubernetes probes не должны требовать аутентификации.
        """
        response = client.get("/health/live")

        assert response.status_code == status.HTTP_200_OK

    def test_readiness_no_auth_required(self, client):
        """
        Тест: Readiness доступен без Authorization header.
        """
        with patch("app.db.database.check_db_health", new_callable=AsyncMock) as mock_db:
            mock_db.return_value = True
            with patch("app.services.cache_service.cache_service") as mock_cache:
                mock_cache.redis_cache = None

                response = client.get("/health/ready")

        assert response.status_code == status.HTTP_200_OK

    def test_liveness_does_not_expose_secrets(self, client):
        """
        Тест: Liveness не раскрывает secrets или внутреннюю информацию.
        """
        response = client.get("/health/live")

        data = response.json()
        # Только минимальная информация
        assert set(data.keys()) == {"status"}

    @pytest.fixture
    def mock_deps_for_security_test(self):
        """Mock dependencies для security тестов."""
        with patch("app.db.database.check_db_health", new_callable=AsyncMock) as mock_db:
            mock_db.return_value = True
            with patch("app.services.cache_service.cache_service") as mock_cache:
                mock_cache.redis_cache = None
                yield

    def test_readiness_does_not_expose_connection_strings(
        self, client, mock_deps_for_security_test
    ):
        """
        Тест: Readiness не раскрывает connection strings или credentials.
        """
        response = client.get("/health/ready")

        data = response.json()
        # Проверяем что нет sensitive полей
        text = str(data).lower()
        assert "password" not in text
        assert "secret" not in text
        assert "credential" not in text
        assert "localhost:5432" not in text  # DB connection string
        assert "redis://" not in text  # Redis connection string
