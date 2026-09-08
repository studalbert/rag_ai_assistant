from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings

engine = create_async_engine(settings.database_url, echo=False, future=True)

# expire_on_commit=False: после commit объекты остаются доступными для чтения
# без лишнего похода в БД (удобно, когда возвращаем объект из сервиса сразу после сохранения)
AsyncSessionLocal = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI-зависимость: одна сессия на один HTTP-запрос."""
    async with AsyncSessionLocal() as session:
        yield session
