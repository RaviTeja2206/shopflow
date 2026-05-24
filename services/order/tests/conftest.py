import os
import uuid
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import text
from unittest.mock import AsyncMock, patch
from jose import jwt
from datetime import datetime, timedelta, timezone

from app.main import app
from app.db.session import get_db
from app.db.base import Base
from app.models.order import Order, OrderItem  # noqa: F401
from app.core.dependencies import get_current_user_id
from app.core.config import settings

TEST_DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql+asyncpg://shopflow:shopflow_secret@postgres:5432/shopflow",
)

TEST_USER_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
TEST_PRODUCT_ID = uuid.UUID("22222222-2222-2222-2222-222222222222")


def make_token(user_id: uuid.UUID = TEST_USER_ID) -> str:
    payload = {
        "sub": str(user_id),
        "type": "access",
        "jti": str(uuid.uuid4()),
        "exp": datetime.now(timezone.utc) + timedelta(minutes=30),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


@pytest_asyncio.fixture(scope="session")
async def test_engine():
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture(scope="session")
async def _session_factory(test_engine):
    return async_sessionmaker(
        bind=test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )


@pytest_asyncio.fixture(autouse=True)
async def clean_tables(_session_factory):
    yield
    async with _session_factory() as session:
        async with session.begin():
            await session.execute(text("DELETE FROM orders.order_items"))
            await session.execute(text("DELETE FROM orders.orders"))


@pytest_asyncio.fixture
async def client(test_engine):
    factory = async_sessionmaker(
        bind=test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )

    async def production_like_get_db():
        async with factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    # Override auth — return fixed user_id without hitting Redis/DB
    async def override_get_current_user_id():
        return TEST_USER_ID

    app.dependency_overrides[get_db] = production_like_get_db
    app.dependency_overrides[get_current_user_id] = override_get_current_user_id

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac

    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def kafka_mock():
    with patch("app.services.order_service.publish", new_callable=AsyncMock) as mock:
        yield mock


@pytest_asyncio.fixture
def mock_product():
    """Default product returned by product service mock."""
    return {
        "id": str(TEST_PRODUCT_ID),
        "name": "MacBook Pro",
        "price": "1299.99",
        "stock_quantity": 10,
        "is_active": True,
    }


@pytest_asyncio.fixture
async def product_mock(mock_product):
    with patch(
        "app.services.order_service.get_product",
        new_callable=AsyncMock,
        return_value=mock_product,
    ) as mock:
        yield mock


@pytest.fixture
def auth_headers():
    return {"Authorization": f"Bearer {make_token()}"}


@pytest.fixture
def order_payload():
    return {
        "items": [{"product_id": str(TEST_PRODUCT_ID), "quantity": 2}],
        "shipping_address": "123 Main St, Hyderabad, Telangana 500001",
    }
