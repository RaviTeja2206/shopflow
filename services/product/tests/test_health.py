from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, patch
from httpx import AsyncClient, ASGITransport
from app.main import app


async def test_health():
    """Smoke test — verify service responds without real Redis."""
    with patch("app.core.redis.get_redis", return_value=AsyncMock()):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test"
        ) as client:
            response = await client.get("/health")
    assert response.status_code == 200
    assert response.json()["service"] == "product-service"
