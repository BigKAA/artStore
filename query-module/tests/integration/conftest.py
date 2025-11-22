"""
Integration Tests - Specific Fixtures.

Дополнительные fixtures для integration тестов:
- Real HTTP client setup
- Database integration fixtures
- Mock external services (Admin Module, Storage Element)
"""

import pytest
from unittest.mock import patch, MagicMock


# ========================================
# Integration-Specific Fixtures
# ========================================

@pytest.fixture(autouse=True)
def mock_cache_service_for_integration():
    """
    Auto-mock cache service для всех integration тестов.

    Это предотвращает реальные Redis подключения в тестах.
    """
    mock_redis = MagicMock()
    mock_redis.ping.return_value = True
    mock_redis.get.return_value = None
    mock_redis.setex.return_value = True
    mock_redis.delete.return_value = 1

    with patch("app.services.cache_service.redis.Redis", return_value=mock_redis):
        yield