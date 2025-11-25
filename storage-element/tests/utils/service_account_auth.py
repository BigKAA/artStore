"""
OAuth 2.0 утилиты для интеграционных тестов с real service account.

Использует test service account из TEST_SERVICE_ACCOUNT.md для получения
реальных OAuth токенов через Admin Module.

Credentials:
- Client ID: sa_dev_test_integration_ser_1ea5433c
- Role: user
- Auth endpoint: POST http://localhost:8000/api/v1/auth/token
"""

import os
from typing import Optional

import httpx


# Test Service Account credentials (из TEST_SERVICE_ACCOUNT.md)
TEST_CLIENT_ID = os.getenv("TEST_CLIENT_ID", "sa_dev_test_integration_ser_1ea5433c")
TEST_CLIENT_SECRET = os.getenv("TEST_CLIENT_SECRET", "6vj(mpptg.C+(9WZ")
AUTH_URL = os.getenv("AUTH_URL", "http://localhost:8000/api/v1/auth/token")


async def get_service_account_token(
    client_id: Optional[str] = None,
    client_secret: Optional[str] = None,
    auth_url: Optional[str] = None,
) -> str:
    """
    Получение access token через OAuth 2.0 Client Credentials flow.

    Выполняет аутентификацию через реальный Admin Module endpoint.

    Args:
        client_id: Client ID service account (по умолчанию из env/константы)
        client_secret: Client Secret (по умолчанию из env/константы)
        auth_url: URL endpoint аутентификации (по умолчанию из env/константы)

    Returns:
        str: JWT access token

    Raises:
        httpx.HTTPStatusError: При ошибке аутентификации (401, 403, и т.д.)
        httpx.RequestError: При сетевых ошибках

    Примеры:
        >>> token = await get_service_account_token()
        >>> headers = create_auth_headers(token)
        >>> response = await client.get("/api/v1/files", headers=headers)
    """
    _client_id = client_id or TEST_CLIENT_ID
    _client_secret = client_secret or TEST_CLIENT_SECRET
    _auth_url = auth_url or AUTH_URL

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            _auth_url,
            json={
                "grant_type": "client_credentials",
                "client_id": _client_id,
                "client_secret": _client_secret,
            },
        )
        response.raise_for_status()
        return response.json()["access_token"]


def create_auth_headers(token: str) -> dict:
    """
    Создание HTTP headers с Authorization Bearer токеном.

    Args:
        token: JWT access token

    Returns:
        dict: HTTP headers с Authorization header

    Примеры:
        >>> token = await get_service_account_token()
        >>> headers = create_auth_headers(token)
        >>> # headers = {"Authorization": "Bearer eyJ..."}
    """
    return {"Authorization": f"Bearer {token}"}


def get_sync_service_account_token(
    client_id: Optional[str] = None,
    client_secret: Optional[str] = None,
    auth_url: Optional[str] = None,
) -> str:
    """
    Синхронная версия получения access token.

    Для использования в synchronous fixtures и утилитах.

    Args:
        client_id: Client ID service account
        client_secret: Client Secret
        auth_url: URL endpoint аутентификации

    Returns:
        str: JWT access token
    """
    _client_id = client_id or TEST_CLIENT_ID
    _client_secret = client_secret or TEST_CLIENT_SECRET
    _auth_url = auth_url or AUTH_URL

    with httpx.Client(timeout=30.0) as client:
        response = client.post(
            _auth_url,
            json={
                "grant_type": "client_credentials",
                "client_id": _client_id,
                "client_secret": _client_secret,
            },
        )
        response.raise_for_status()
        return response.json()["access_token"]
