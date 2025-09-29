from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from app.core.config import settings

# Создаем асинхронный "движок" для SQLAlchemy
engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True)

# Создаем фабрику асинхронных сессий
AsyncSessionLocal = async_sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Зависимость FastAPI для получения асинхронной сессии базы данных.
    """
    async with AsyncSessionLocal() as session:
        yield session