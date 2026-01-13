"""
Shared test fixtures для E2E integration tests.

Provides:
- Database client access
- Auth token generation
- Common test utilities
"""

import os
import pytest
import httpx
import asyncio


# ==============================================================================
# Configuration
# ==============================================================================

# Get client_id dynamically from environment or use fallback
TEST_CLIENT_ID = os.getenv("TEST_CLIENT_ID", "sa_prod_admin_service_11710636")
TEST_CLIENT_SECRET = os.getenv("TEST_CLIENT_SECRET", "Test-Password123")

ADMIN_MODULE_URL = "http://localhost:8000"


# ==============================================================================
# Fixtures
# ==============================================================================

@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
async def auth_token() -> str:
    """
    Session-scoped JWT token для E2E tests.

    Получает token один раз для всей test session.
    """
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{ADMIN_MODULE_URL}/api/v1/auth/token",
            json={
                "client_id": TEST_CLIENT_ID,
                "client_secret": TEST_CLIENT_SECRET,
            },
            timeout=10.0
        )

        if response.status_code != 200:
            pytest.fail(f"Failed to get auth token: {response.status_code} - {response.text}")

        data = response.json()
        return data["access_token"]


@pytest.fixture
def test_client_id() -> str:
    """Get test client ID."""
    return TEST_CLIENT_ID


@pytest.fixture
def test_client_secret() -> str:
    """Get test client secret."""
    return TEST_CLIENT_SECRET
