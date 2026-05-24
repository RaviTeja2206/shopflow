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
from app.models.product import Product, Category  # noqa: F401
from app.core.config import settings

TEST_DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql+asyncpg://shopflow:shopflow_secret@postgres:5432/shopflow",
)

TEST_USER_ID  = uuid.UUID("11111111-1111-1111-1111-111111111111")
TEST_ADMIN_ID = uuid.UUID("22222222-2222-2222-2222-222222222222")


def make_token(user_id: uuid.UUID, role: str = "user") -> str:
    payload = {
        "sub": str(user_id),
        "type": "access",
        "role": role,
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
            await session.execute(text("DELETE FROM products.products"))
            await session.execute(text("DELETE FROM products.categories"))


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

    app.dependency_overrides[get_db] = production_like_get_db

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac

    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def redis_mock():
    redis = AsyncMock()
    redis.get.return_value = None
    redis.set.return_value = True
    redis.setex.return_value = True
    redis.delete.return_value = True
    redis.exists.return_value = False
    redis.keys.return_value = []

    with patch("app.core.redis.get_redis", return_value=redis):
        yield redis


@pytest.fixture
def admin_headers():
    return {"Authorization": f"Bearer {make_token(TEST_ADMIN_ID, role='admin')}"}


@pytest.fixture
def user_headers():
    return {"Authorization": f"Bearer {make_token(TEST_USER_ID, role='user')}"}


@pytest.fixture
def category_data():
    return {"name": "Electronics", "description": "Electronic devices"}


@pytest.fixture
def product_data():
    return {
        "name": "MacBook Pro",
        "description": "Apple laptop",
        "price": "1299.99",
        "stock_quantity": 10,
    }
