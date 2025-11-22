"""
Database session management для async SQLAlchemy.

Управление подключением к PostgreSQL с connection pooling.
"""

import logging
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.pool import NullPool

from app.core.config import settings

logger = logging.getLogger(__name__)

# Создание async engine с connection pooling
engine = create_async_engine(
    settings.database.url,
    echo=settings.app.debug,  # SQL логирование в debug режиме
    pool_size=settings.database.pool_size,
    max_overflow=settings.database.max_overflow,
    pool_timeout=settings.database.pool_timeout,
    pool_recycle=settings.database.pool_recycle,
    pool_pre_ping=True,  # Проверка соединения перед использованием
)

# Создание session maker
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency для получения database session.

    Использование в FastAPI:
        @app.get("/items")
        async def get_items(db: AsyncSession = Depends(get_db)):
            ...

    Yields:
        AsyncSession: Database session

    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db() -> None:
    """
    Инициализация базы данных.

    Создание всех таблиц если они не существуют.
    Используется при старте приложения.
    """
    from app.db.base import Base

    async with engine.begin() as conn:
        # Создание всех таблиц
        await conn.run_sync(Base.metadata.create_all)

    logger.info("Database initialized successfully")


async def close_db() -> None:
    """
    Закрытие соединений с базой данных.

    Вызывается при остановке приложения.
    """
    await engine.dispose()
    logger.info("Database connections closed")
