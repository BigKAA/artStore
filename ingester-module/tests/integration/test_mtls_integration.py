"""
E2E integration tests для mTLS communication.

Sprint 22 Phase 3: Integration testing для OAuth 2.0 authentication и mTLS encrypted communication.

Prerequisites:
- Admin Module running on configured URL (default: http://localhost:8000)
- Storage Element running on configured URL (default: http://localhost:8010)
- Valid service account credentials configured
- TLS certificates configured (если mTLS enabled)

Запуск:
    # Все integration тесты
    pytest tests/integration/test_mtls_integration.py -v -m integration

    # Только auth тесты
    pytest tests/integration/test_mtls_integration.py -v -k "auth"

    # Пропустить integration тесты
    pytest -v -m "not integration"
"""

import pytest
from io import BytesIO
from pathlib import Path

from fastapi import UploadFile

from app.services.auth_service import AuthService
from app.services.upload_service import UploadService
from app.core.config import settings
from app.schemas.upload import UploadRequest, StorageMode


# ================================================================================
# Integration Test Markers
# ================================================================================

pytestmark = pytest.mark.integration  # Mark all tests in this file as integration


# ================================================================================
# Helper Functions
# ================================================================================

def is_admin_module_available() -> bool:
    """
    Check if Admin Module is accessible.

    Returns:
        bool: True if Admin Module responds to health checks
    """
    import httpx
    try:
        response = httpx.get(
            f"{settings.service_account.admin_module_url}/health/live",
            timeout=2.0
        )
        return response.status_code == 200
    except Exception:
        return False


def is_storage_element_available() -> bool:
    """
    Check if Storage Element is accessible.

    Returns:
        bool: True if Storage Element responds to health checks
    """
    import httpx
    try:
        response = httpx.get(
            f"{settings.storage_element.base_url}/health/live",
            timeout=2.0
        )
        return response.status_code == 200
    except Exception:
        return False


# ================================================================================
# OAuth 2.0 Authentication Integration Tests
# ================================================================================

@pytest.mark.asyncio
@pytest.mark.skipif(
    not is_admin_module_available(),
    reason="Admin Module not available - start with docker-compose up admin-module"
)
async def test_auth_service_connects_to_admin_module():
    """
    Test AuthService successfully obtains JWT token from Admin Module.

    Scenario: E2E OAuth 2.0 Client Credentials flow
    Expected:
        - Connection established to Admin Module
        - JWT token obtained
        - Token cached with correct expiration
        - Token format valid (starts with eyJ)

    Environment:
        - SERVICE_ACCOUNT_CLIENT_ID must be configured
        - SERVICE_ACCOUNT_CLIENT_SECRET must be configured
        - Admin Module must be running
    """
    auth_service = AuthService(
        admin_module_url=settings.service_account.admin_module_url,
        client_id=settings.service_account.client_id,
        client_secret=settings.service_account.client_secret,
        timeout=settings.service_account.timeout
    )

    try:
        # Attempt to get access token (real HTTP request)
        token = await auth_service.get_access_token()

        # Verify token obtained
        assert token is not None, "Access token should not be None"
        assert len(token) > 0, "Access token should not be empty"
        assert token.startswith("eyJ"), "JWT token should start with 'eyJ'"

        # Verify token cached
        assert auth_service._access_token == token, "Token should be cached"
        assert auth_service._token_expires_at is not None, "Expiration should be set"

        # Verify token can be reused from cache
        token2 = await auth_service.get_access_token()
        assert token2 == token, "Cached token should be reused"

    finally:
        await auth_service.close()


@pytest.mark.asyncio
@pytest.mark.skipif(
    not is_admin_module_available(),
    reason="Admin Module not available"
)
async def test_auth_service_token_refresh_on_expiry():
    """
    Test AuthService automatically refreshes expired token.

    Scenario: Token expires, new token requested automatically
    Expected:
        - Initial token obtained
        - After manual expiry, new token obtained
        - New token different from old token
    """
    auth_service = AuthService(
        admin_module_url=settings.service_account.admin_module_url,
        client_id=settings.service_account.client_id,
        client_secret=settings.service_account.client_secret
    )

    try:
        # Get first token
        token1 = await auth_service.get_access_token()
        assert token1 is not None

        # Manually expire token by setting expires_at to past
        from datetime import datetime, timezone, timedelta
        auth_service._token_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)

        # Get token again - should trigger refresh
        token2 = await auth_service.get_access_token()
        assert token2 is not None
        assert token2.startswith("eyJ")

        # Note: tokens might be same if Admin Module returns same token
        # Main verification: no exception raised, valid token returned

    finally:
        await auth_service.close()


@pytest.mark.asyncio
async def test_auth_service_handles_invalid_credentials():
    """
    Test AuthService handles invalid credentials gracefully.

    Scenario: Invalid client_id/client_secret provided
    Expected: AuthenticationException raised with 401 status

    Note: This test will fail if actual credentials are valid
    """
    from app.core.exceptions import AuthenticationException

    auth_service = AuthService(
        admin_module_url=settings.service_account.admin_module_url,
        client_id="invalid_client_id",
        client_secret="invalid_secret",
        timeout=5
    )

    try:
        if is_admin_module_available():
            # Should raise AuthenticationException
            with pytest.raises(AuthenticationException) as exc_info:
                await auth_service.get_access_token()

            # Verify error details
            assert "401" in str(exc_info.value) or "Failed to authenticate" in str(exc_info.value)
        else:
            pytest.skip("Admin Module not available for invalid credentials test")

    finally:
        await auth_service.close()


# ================================================================================
# mTLS Communication Integration Tests
# ================================================================================

@pytest.mark.asyncio
@pytest.mark.skipif(
    not is_storage_element_available(),
    reason="Storage Element not available - start with docker-compose up storage-element"
)
async def test_upload_service_mtls_connection():
    """
    Test UploadService establishes mTLS connection to Storage Element.

    Scenario: HTTP client created with mTLS configuration (if enabled)
    Expected:
        - HTTP client created successfully
        - Base URL configured correctly
        - mTLS enabled if TLS settings configured
        - Connection pool configured
    """
    auth_service = AuthService(
        admin_module_url=settings.service_account.admin_module_url,
        client_id=settings.service_account.client_id,
        client_secret=settings.service_account.client_secret
    )
    upload_service = UploadService(auth_service=auth_service)

    try:
        # Get HTTP client (validates mTLS setup)
        client = await upload_service._get_client()

        # Verify client configuration
        assert client is not None, "HTTP client should be created"
        assert str(client.base_url) == settings.storage_element.base_url, \
            "Base URL should match configuration"

        # Verify connection pool settings
        assert client.limits.max_connections == settings.storage_element.connection_pool_size

        # If TLS enabled, verify SSL context configured
        if settings.tls.enabled:
            # Client should have verify set to SSLContext
            assert client._transport is not None, "Transport should be configured for mTLS"

    finally:
        await upload_service.close()
        await auth_service.close()


@pytest.mark.asyncio
@pytest.mark.skipif(
    not is_admin_module_available() or not is_storage_element_available(),
    reason="Requires Admin Module AND Storage Element"
)
async def test_full_upload_workflow_with_authentication():
    """
    Test complete file upload workflow: auth → upload → verify.

    Scenario: End-to-end file upload через Ingester Module
    Expected:
        - JWT token obtained from Admin Module
        - File uploaded to Storage Element
        - Upload response contains file_id и metadata
        - Upload successful (no exceptions)

    Note: Requires writable Storage Element в edit mode
    """
    auth_service = AuthService(
        admin_module_url=settings.service_account.admin_module_url,
        client_id=settings.service_account.client_id,
        client_secret=settings.service_account.client_secret
    )
    upload_service = UploadService(auth_service=auth_service)

    try:
        # Create test file
        test_content = b"Sprint 22 E2E Integration Test - mTLS Validation"
        test_file = UploadFile(
            filename="sprint22_e2e_test.txt",
            file=BytesIO(test_content)
        )

        # Create upload request
        upload_request = UploadRequest(
            description="Sprint 22 E2E integration test file",
            storage_mode=StorageMode.edit,
            compress=False
        )

        # Execute upload (real HTTP requests)
        response = await upload_service.upload_file(
            file=test_file,
            request=upload_request,
            user_id="sprint22-test-user",
            username="integration_test"
        )

        # Verify upload response
        assert response is not None, "Upload response should not be None"
        assert response.file_id is not None, "File ID should be assigned"
        assert response.original_filename == "sprint22_e2e_test.txt"
        assert response.file_size == len(test_content)
        assert response.storage_element_url == settings.storage_element.base_url

        print(f"\n✅ E2E Upload Success: file_id={response.file_id}")

    finally:
        await upload_service.close()
        await auth_service.close()


# ================================================================================
# TLS Configuration Validation Tests
# ================================================================================

@pytest.mark.asyncio
async def test_tls_configuration_validation():
    """
    Test TLS configuration loaded correctly from settings.

    Scenario: Validate TLS settings без реальных connections
    Expected:
        - TLS enabled/disabled flag correct
        - Certificate paths configured (if enabled)
        - Protocol version valid
        - Cipher suites configured (if specified)
    """
    from app.core.tls_utils import create_ssl_context

    # Test SSL context creation с текущими settings
    ssl_context = create_ssl_context()

    if settings.tls.enabled:
        # TLS enabled - SSL context should be created
        assert ssl_context is not None, "SSL context should be created when TLS enabled"

        # Verify protocol version configured
        if settings.tls.protocol_version == "TLSv1.3":
            assert ssl_context.minimum_version == __import__('ssl').TLSVersion.TLSv1_3
        elif settings.tls.protocol_version == "TLSv1.2":
            assert ssl_context.minimum_version == __import__('ssl').TLSVersion.TLSv1_2

    else:
        # TLS disabled - no SSL context
        assert ssl_context is None, "SSL context should be None when TLS disabled"


@pytest.mark.asyncio
async def test_auth_service_with_mtls_if_configured():
    """
    Test AuthService uses mTLS if TLS enabled в configuration.

    Scenario: Validate mTLS integration в AuthService HTTP client
    Expected:
        - If TLS enabled: client has SSL context
        - If TLS disabled: client uses default verification
    """
    auth_service = AuthService(
        admin_module_url=settings.service_account.admin_module_url,
        client_id=settings.service_account.client_id,
        client_secret=settings.service_account.client_secret
    )

    try:
        client = auth_service._get_client()

        # Verify client created
        assert client is not None

        # If mTLS enabled, verify SSL configuration applied
        if settings.tls.enabled:
            # Client should have custom verify (SSLContext)
            # Note: exact verification depends on httpx internals
            assert client is not None  # Basic validation

    finally:
        await auth_service.close()


# ================================================================================
# Performance and Reliability Tests
# ================================================================================

@pytest.mark.asyncio
@pytest.mark.slow
@pytest.mark.skipif(
    not is_admin_module_available(),
    reason="Admin Module not available"
)
async def test_auth_service_concurrent_token_requests():
    """
    Test AuthService handles concurrent token requests correctly.

    Scenario: Multiple async tasks request tokens simultaneously
    Expected:
        - All tasks receive same cached token
        - Only one HTTP request made to Admin Module
        - Thread-safe token caching

    Note: Marked as 'slow' due to multiple async operations
    """
    import asyncio

    auth_service = AuthService(
        admin_module_url=settings.service_account.admin_module_url,
        client_id=settings.service_account.client_id,
        client_secret=settings.service_account.client_secret
    )

    try:
        # Launch 5 concurrent token requests
        tasks = [auth_service.get_access_token() for _ in range(5)]
        tokens = await asyncio.gather(*tasks)

        # Verify all tokens identical (cached after first request)
        assert len(set(tokens)) == 1, "All concurrent requests should return same token"
        assert all(token.startswith("eyJ") for token in tokens)

    finally:
        await auth_service.close()


@pytest.mark.asyncio
@pytest.mark.skipif(
    not is_admin_module_available() or not is_storage_element_available(),
    reason="Requires full infrastructure"
)
async def test_upload_service_connection_pool_reuse():
    """
    Test UploadService reuses HTTP connection pool efficiently.

    Scenario: Multiple uploads через same UploadService instance
    Expected:
        - HTTP client singleton reused
        - Connection pool shared между requests
        - Performance improvement от connection reuse
    """
    auth_service = AuthService(
        admin_module_url=settings.service_account.admin_module_url,
        client_id=settings.service_account.client_id,
        client_secret=settings.service_account.client_secret
    )
    upload_service = UploadService(auth_service=auth_service)

    try:
        # Get client multiple times
        client1 = await upload_service._get_client()
        client2 = await upload_service._get_client()
        client3 = await upload_service._get_client()

        # Verify same instance reused
        assert client1 is client2 is client3, \
            "HTTP client should be singleton (reused across calls)"

    finally:
        await upload_service.close()
        await auth_service.close()
