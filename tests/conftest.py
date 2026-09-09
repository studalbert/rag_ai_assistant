import os
from collections.abc import AsyncGenerator

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.db import get_db
from app.main import app
from app.models import Base

TEST_DATABASE_URL = os.environ["TEST_DATABASE_URL"]

# NullPool: не переиспользуем соединения между тестами. Без этого asyncpg-соединения
# остаются привязаны к event loop'у, в котором были созданы, а pytest-asyncio создаёт
# новый event loop для каждого теста — из-за этого вылезает
# "cannot perform operation: another operation is in progress".
test_engine = create_async_engine(TEST_DATABASE_URL, future=True, poolclass=NullPool)
TestSessionLocal = async_sessionmaker(
    bind=test_engine, class_=AsyncSession, expire_on_commit=False
)


@pytest_asyncio.fixture(autouse=True)
async def prepare_database() -> AsyncGenerator[None, None]:
    """Пересоздаёт схему перед каждым тестом.

    Для небольшого набора тестов это проще и надёжнее, чем разбираться
    с транзакциями/роллбэками на async-сессиях. Когда тестов станет
    много и пересоздание схемы станет заметно тормозить — можно
    оптимизировать до truncate таблиц вместо drop/create.
    """
    async with test_engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.create_all)

    yield

    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


async def _override_get_db() -> AsyncGenerator[AsyncSession, None]:
    async with TestSessionLocal() as session:
        yield session


# Подменяем реальную зависимость get_db на тестовую версию для всего приложения
app.dependency_overrides[get_db] = _override_get_db


@pytest_asyncio.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
