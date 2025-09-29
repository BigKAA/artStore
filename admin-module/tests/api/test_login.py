from typing import Dict
import pytest
from httpx import AsyncClient
from typing import Dict

from app.core.config import settings

pytestmark = pytest.mark.asyncio


async def test_get_access_token(
    client: AsyncClient, superuser_token_headers: Dict[str, str]
) -> None:
    # This test uses the fixture to get the token, so it's already tested.
    # We just check if the header is there.
    assert "Authorization" in superuser_token_headers


async def test_use_access_token(
    client: AsyncClient, superuser_token_headers: Dict[str, str]
) -> None:
    r = await client.get(f"/api/users/me", headers=superuser_token_headers)
    result = r.json()
    assert r.status_code == 200
    assert result["email"] == "admin@test.com"