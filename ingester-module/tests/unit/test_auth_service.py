"""
Unit tests для AuthService.

Sprint 22 Phase 1: Comprehensive test coverage для OAuth 2.0 authentication service.
Target: 90%+ statement coverage.
"""

import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch, MagicMock

from app.services.auth_service import AuthService
from app.core.exceptions import AuthenticationException


@pytest.fixture
def auth_service():
    """
    Create AuthService instance для тестирования.

    Returns:
        AuthService с test configuration
    """
    return AuthService(
        admin_module_url="http://test-admin:8000",
        client_id="test_client_id",
        client_secret="test_secret",
        timeout=10
    )


# ================================================================================
# Token Acquisition Success Scenarios
# ================================================================================

@pytest.mark.asyncio
async def test_get_access_token_success(auth_service):
    """
    Test successful token acquisition from Admin Module.

    Scenario: First token request с пустым cache
    Expected: Token obtained и cached
    """
    # Mock HTTP response
    mock_response = MagicMock()  # httpx.Response is not async
    mock_response.json.return_value = {
        "access_token": "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.test.token",
        "token_type": "Bearer",
        "expires_in": 1800
    }

    # Mock HTTP client
    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)

    with patch.object(auth_service, '_get_client', return_value=mock_client):
        token = await auth_service.get_access_token()

        # Verify token returned
        assert token == "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.test.token"

        # Verify token cached
        assert auth_service._access_token == token
        assert auth_service._token_expires_at is not None

        # Verify expiration set correctly (1800 seconds from now)
        expected_expiry = datetime.now(timezone.utc) + timedelta(seconds=1800)
        assert abs((auth_service._token_expires_at - expected_expiry).total_seconds()) < 5

        # Verify HTTP call made with correct parameters
        mock_client.post.assert_called_once_with(
            "/api/v1/auth/token",
            json={
                "client_id": "test_client_id",
                "client_secret": "test_secret"
            },
            headers={"Content-Type": "application/json"}
        )


@pytest.mark.asyncio
async def test_get_access_token_uses_cache_when_valid(auth_service):
    """
    Test that cached token is reused when still valid.

    Scenario: Token cached с expiry в 10 минут (>5 min threshold)
    Expected: Cached token returned, NO HTTP call
    """
    # Set cached token (expires in 10 minutes - valid)
    auth_service._access_token = "cached_token_12345"
    auth_service._token_expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)

    # Mock HTTP client (should NOT be called)
    mock_client = AsyncMock()
    mock_client.post = AsyncMock()

    with patch.object(auth_service, '_get_client', return_value=mock_client):
        token = await auth_service.get_access_token()

        # Verify cached token returned
        assert token == "cached_token_12345"

        # Verify NO HTTP call made
        mock_client.post.assert_not_called()


@pytest.mark.asyncio
async def test_get_access_token_refreshes_when_expiring_soon(auth_service):
    """
    Test token refresh when cached token expires in <5 minutes.

    Scenario: Token cached с expiry в 3 минуты (<5 min threshold)
    Expected: New token requested, old token replaced
    """
    # Set cached token (expires in 3 minutes - invalid due to 5min threshold)
    auth_service._access_token = "old_token"
    auth_service._token_expires_at = datetime.now(timezone.utc) + timedelta(minutes=3)

    # Mock HTTP response with new token
    mock_response = MagicMock()  # httpx.Response is not async
    mock_response.json.return_value = {
        "access_token": "new_token_67890",
        "expires_in": 1800
    }

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)

    with patch.object(auth_service, '_get_client', return_value=mock_client):
        token = await auth_service.get_access_token()

        # Verify new token returned
        assert token == "new_token_67890"

        # Verify HTTP call made for refresh
        mock_client.post.assert_called_once()


# ================================================================================
# Error Handling Tests
# ================================================================================

@pytest.mark.asyncio
async def test_get_access_token_http_401_error(auth_service):
    """
    Test authentication failure with HTTP 401 Unauthorized.

    Scenario: Admin Module возвращает 401 (invalid credentials)
    Expected: AuthenticationException raised с details
    """
    import httpx

    # Mock HTTP 401 response
    mock_response = MagicMock()
    mock_response.status_code = 401
    mock_response.text = "Invalid credentials"

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(
        side_effect=httpx.HTTPStatusError(
            "Unauthorized",
            request=MagicMock(),
            response=mock_response
        )
    )

    with patch.object(auth_service, '_get_client', return_value=mock_client):
        with pytest.raises(AuthenticationException) as exc_info:
            await auth_service.get_access_token()

        # Verify exception message contains HTTP status
        assert "Failed to authenticate" in str(exc_info.value)
        assert "401" in str(exc_info.value)


@pytest.mark.asyncio
async def test_get_access_token_http_500_error(auth_service):
    """
    Test Admin Module server error handling.

    Scenario: Admin Module возвращает 500 Internal Server Error
    Expected: AuthenticationException raised
    """
    import httpx

    mock_response = MagicMock()
    mock_response.status_code = 500
    mock_response.text = "Internal Server Error"

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(
        side_effect=httpx.HTTPStatusError(
            "Server Error",
            request=MagicMock(),
            response=mock_response
        )
    )

    with patch.object(auth_service, '_get_client', return_value=mock_client):
        with pytest.raises(AuthenticationException) as exc_info:
            await auth_service.get_access_token()

        # Verify exception raised
        assert "Failed to authenticate" in str(exc_info.value)


@pytest.mark.asyncio
async def test_get_access_token_connection_error(auth_service):
    """
    Test Admin Module connection failure.

    Scenario: Cannot connect to Admin Module (network error)
    Expected: AuthenticationException с connection details
    """
    import httpx

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(
        side_effect=httpx.ConnectError("Connection refused")
    )

    with patch.object(auth_service, '_get_client', return_value=mock_client):
        with pytest.raises(AuthenticationException) as exc_info:
            await auth_service.get_access_token()

        # Verify exception message
        assert "Cannot connect to Admin Module" in str(exc_info.value)


@pytest.mark.asyncio
async def test_get_access_token_timeout_error(auth_service):
    """
    Test Admin Module request timeout.

    Scenario: Request to Admin Module times out
    Expected: AuthenticationException raised
    """
    import httpx

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(
        side_effect=httpx.TimeoutException("Request timeout")
    )

    with patch.object(auth_service, '_get_client', return_value=mock_client):
        with pytest.raises(AuthenticationException):
            await auth_service.get_access_token()


@pytest.mark.asyncio
async def test_get_access_token_invalid_response_missing_token(auth_service):
    """
    Test invalid response from Admin Module (missing access_token).

    Scenario: Response JSON не содержит поле access_token
    Expected: AuthenticationException raised
    """
    mock_response = MagicMock()  # httpx.Response is not async
    mock_response.json.return_value = {
        "token_type": "Bearer",
        "expires_in": 1800
        # Missing "access_token" field!
    }

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)

    with patch.object(auth_service, '_get_client', return_value=mock_client):
        with pytest.raises(AuthenticationException) as exc_info:
            await auth_service.get_access_token()

        # Verify exception message
        assert "Invalid token response" in str(exc_info.value)


@pytest.mark.asyncio
async def test_get_access_token_invalid_json_response(auth_service):
    """
    Test invalid JSON response from Admin Module.

    Scenario: Response не является валидным JSON
    Expected: AuthenticationException raised
    """
    mock_response = MagicMock()  # httpx.Response is not async
    mock_response.json.side_effect = ValueError("Invalid JSON")

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)

    with patch.object(auth_service, '_get_client', return_value=mock_client):
        with pytest.raises(AuthenticationException) as exc_info:
            await auth_service.get_access_token()

        # Verify exception raised
        assert "Invalid token response" in str(exc_info.value)


# ================================================================================
# Token Lifecycle Tests
# ================================================================================

def test_is_token_valid_with_no_token(auth_service):
    """
    Test token validation when no token cached.

    Scenario: _access_token is None
    Expected: Returns False
    """
    assert auth_service._is_token_valid() is False


def test_is_token_valid_with_expired_token(auth_service):
    """
    Test token validation when token expired.

    Scenario: Token expiry в прошлом
    Expected: Returns False
    """
    auth_service._access_token = "expired_token"
    auth_service._token_expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)

    assert auth_service._is_token_valid() is False


def test_is_token_valid_with_expiring_soon_token(auth_service):
    """
    Test token validation when token expires in <5 minutes.

    Scenario: Token expiry в 4 минуты (below 5-minute threshold)
    Expected: Returns False (triggers proactive refresh)
    """
    auth_service._access_token = "expiring_soon_token"
    # Expires in 4 minutes - below 5 minute threshold
    auth_service._token_expires_at = datetime.now(timezone.utc) + timedelta(minutes=4)

    assert auth_service._is_token_valid() is False


def test_is_token_valid_with_valid_token(auth_service):
    """
    Test token validation when token still valid (>5 min to expiry).

    Scenario: Token expiry в 10 минут (above 5-minute threshold)
    Expected: Returns True
    """
    auth_service._access_token = "valid_token"
    # Expires in 10 minutes - above 5 minute threshold
    auth_service._token_expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)

    assert auth_service._is_token_valid() is True


def test_is_token_valid_exactly_at_threshold(auth_service):
    """
    Test token validation exactly at 5-minute threshold.

    Scenario: Token expiry ровно в 5 минут
    Expected: Returns False (threshold not inclusive)
    """
    auth_service._access_token = "threshold_token"
    auth_service._token_expires_at = datetime.now(timezone.utc) + timedelta(minutes=5)

    # At exactly 5 minutes, should trigger refresh (not inclusive)
    assert auth_service._is_token_valid() is False


# ================================================================================
# Resource Management Tests
# ================================================================================

@pytest.mark.asyncio
async def test_close_cleanup(auth_service):
    """
    Test proper cleanup on close.

    Scenario: Service with cached token и HTTP client
    Expected: All resources cleaned up
    """
    # Setup cached token and client
    auth_service._access_token = "test_token"
    auth_service._token_expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)

    mock_client = AsyncMock()
    auth_service._client = mock_client

    # Call close
    await auth_service.close()

    # Verify cleanup
    assert auth_service._access_token is None
    assert auth_service._token_expires_at is None
    mock_client.aclose.assert_called_once()


def test_get_client_creates_client_once(auth_service):
    """
    Test HTTP client created only once and reused.

    Scenario: Multiple calls to _get_client()
    Expected: Same instance returned each time
    """
    client1 = auth_service._get_client()
    client2 = auth_service._get_client()

    # Verify same instance returned
    assert client1 is client2


def test_auth_service_initialization(auth_service):
    """
    Test AuthService initialization with configuration.

    Scenario: Create AuthService с parameters
    Expected: Configuration stored correctly
    """
    assert auth_service.admin_module_url == "http://test-admin:8000"
    assert auth_service.client_id == "test_client_id"
    assert auth_service.client_secret == "test_secret"
    assert auth_service.timeout == 10

    # Verify initial state
    assert auth_service._access_token is None
    assert auth_service._token_expires_at is None
    assert auth_service._client is None


# ================================================================================
# Edge Cases and Boundary Conditions
# ================================================================================

@pytest.mark.asyncio
async def test_get_access_token_with_default_expires_in(auth_service):
    """
    Test token acquisition когда expires_in missing from response.

    Scenario: Admin Module response без expires_in field
    Expected: Default 1800 seconds (30 min) используется
    """
    mock_response = MagicMock()  # httpx.Response is not async
    mock_response.json.return_value = {
        "access_token": "token_without_expiry"
        # Missing "expires_in" field
    }

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)

    with patch.object(auth_service, '_get_client', return_value=mock_client):
        token = await auth_service.get_access_token()

        # Verify token obtained
        assert token == "token_without_expiry"

        # Verify default expiry используется (1800 seconds)
        expected_expiry = datetime.now(timezone.utc) + timedelta(seconds=1800)
        assert abs((auth_service._token_expires_at - expected_expiry).total_seconds()) < 5


@pytest.mark.asyncio
async def test_get_access_token_with_very_short_expiry(auth_service):
    """
    Test token с очень коротким сроком действия.

    Scenario: Token expiry 60 seconds (<5 min threshold)
    Expected: Token cached но immediately considered invalid
    """
    mock_response = MagicMock()  # httpx.Response is not async
    mock_response.json.return_value = {
        "access_token": "short_lived_token",
        "expires_in": 60  # Only 60 seconds
    }

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)

    with patch.object(auth_service, '_get_client', return_value=mock_client):
        token = await auth_service.get_access_token()

        # Verify token obtained
        assert token == "short_lived_token"

        # Verify token immediately invalid (< 5 min threshold)
        assert auth_service._is_token_valid() is False
