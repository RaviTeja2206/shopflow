import httpx

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

# Reusable async client — created once, reused across requests
# Like a connection pool but for HTTP
_client: httpx.AsyncClient | None = None


async def get_http_client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(
            timeout=httpx.Timeout(5.0),   # 5 second timeout — fail fast
            limits=httpx.Limits(
                max_connections=100,
                max_keepalive_connections=20,
            ),
        )
    return _client


async def close_http_client():
    global _client
    if _client and not _client.is_closed:
        await _client.aclose()
        _client = None


async def get_product(product_id: str) -> dict | None:
    """
    Fetch product details from product service.
    Returns None if product not found.
    Raises HTTPException if product service is unreachable.
    """
    client = await get_http_client()
    try:
        response = await client.get(
            f"{settings.product_service_url}/api/v1/products/{product_id}"
        )
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return response.json()
    except httpx.TimeoutException:
        logger.error("product_service_timeout", product_id=product_id)
        raise
    except httpx.HTTPStatusError as e:
        logger.error("product_service_error", status=e.response.status_code)
        raise
