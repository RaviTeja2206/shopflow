from unittest.mock import AsyncMock, patch, MagicMock
from httpx import AsyncClient, ASGITransport
from app.main import app


async def test_health():
    """Smoke test — verify service responds without real Kafka/Redis."""
    with patch("app.core.kafka_producer.get_producer", return_value=AsyncMock()), \
         patch("app.core.http_client.get_http_client", return_value=AsyncMock()):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test"
        ) as client:
            response = await client.get("/health")
    assert response.status_code == 200
    assert response.json()["service"] == "order-service"
