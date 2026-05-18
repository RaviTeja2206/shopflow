import os
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import text
from unittest.mock import AsyncMock, patch

from app.main import app
from app.db.session import get_db
from app.db.base import Base
from app.models import User, RefreshToken  # noqa: F401

# Use DATABASE_URL from environment (set by CI) or fall back to local Docker URL
TEST_DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql+asyncpg://shopflow:shopflow_secret@postgres:5432/shopflow"
)


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
def session_factory(test_engine):
    return async_sessionmaker(
        bind=test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )


@pytest_asyncio.fixture(autouse=True)
async def clean_tables(session_factory):
    yield
    async with session_factory() as session:
        async with session.begin():
            await session.execute(text("DELETE FROM users.refresh_tokens"))
            await session.execute(text("DELETE FROM users.users"))


@pytest_asyncio.fixture
async def client(session_factory):
    factory = async_sessionmaker(
        bind=session_factory.kw["bind"],
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )

    async def production_like_get_db():
        async with factory() as s:
            try:
                yield s
                await s.commit()
            except Exception:
                await s.rollback()
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
    redis.exists.return_value = False
    redis.setex.return_value = True

    with patch("app.core.redis.get_redis", return_value=redis), \
         patch("app.core.dependencies.get_redis", return_value=redis), \
         patch("app.services.user_service.get_redis", return_value=redis):
        yield redis


@pytest.fixture
def user_data():
    return {
        "email": "test@shopflow.com",
        "password": "Secret123",
        "full_name": "Test User",
    }
