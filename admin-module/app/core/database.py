"""
Подключение к PostgreSQL через SQLAlchemy async engine.
Поддерживает connection pooling и health checks.
"""

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import QueuePool
from sqlalchemy import text
from typing import AsyncGenerator, Generator
import logging

from .config import settings

logger = logging.getLogger(__name__)

# Создаем async engine с connection pooling
engine = create_async_engine(
    settings.database.url,
    echo=settings.database.echo,
    pool_pre_ping=True,  # Проверка соединения перед использованием
    pool_size=settings.database.pool_size,
    max_overflow=settings.database.max_overflow,
    # poolclass не указываем для async engine - SQLAlchemy автоматически использует AsyncAdaptedQueuePool
    connect_args={"ssl": False},  # Отключаем SSL для локальной разработки
)

# Создаем фабрику сессий
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)

# Создаем синхронный engine для background задач (APScheduler)
sync_engine = create_engine(
    settings.database.sync_url,
    echo=settings.database.echo,
    pool_pre_ping=True,
    pool_size=settings.database.pool_size,
    max_overflow=settings.database.max_overflow,
    poolclass=QueuePool,
)

# Создаем синхронную фабрику сессий для background задач
SyncSessionLocal = sessionmaker(
    bind=sync_engine,
    class_=Session,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency для получения database session в FastAPI endpoints.

    Yields:
        AsyncSession: SQLAlchemy async session

    Example:
        @app.get("/users")
        async def get_users(db: AsyncSession = Depends(get_db)):
            result = await db.execute(select(User))
            return result.scalars().all()
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


def get_sync_session() -> Generator[Session, None, None]:
    """
    Генератор для получения синхронной database session.
    Используется в background задачах (APScheduler) и миграциях.

    Yields:
        Session: SQLAlchemy sync session

    Example:
        sync_session = next(get_sync_session())
        try:
            # Работа с сессией
            user = sync_session.query(User).first()
            sync_session.commit()
        except Exception:
            sync_session.rollback()
            raise
        finally:
            sync_session.close()
    """
    session = SyncSessionLocal()
    try:
        yield session
    except Exception:
        session.rollback()
        raise
    finally:
        session.commit()
        session.close()


async def check_db_connection() -> bool:
    """
    Проверка подключения к базе данных.
    Используется в health checks.

    Returns:
        bool: True если подключение работает, False иначе
    """
    try:
        async with engine.begin() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception as e:
        logger.error(f"Database connection check failed: {e}")
        return False


async def init_db() -> None:
    """
    Инициализация базы данных.
    Создает все таблицы если они не существуют.

    ВАЖНО: В production используйте Alembic миграции вместо этого метода!
    """
    from app.models import Base

    async with engine.begin() as conn:
        # В development режиме можно создавать таблицы автоматически
        if settings.debug:
            await conn.run_sync(Base.metadata.create_all)
            logger.info("Database tables created (debug mode)")
        else:
            logger.info("Skipping table creation in production mode. Use Alembic migrations instead.")


async def close_db() -> None:
    """
    Закрытие подключения к базе данных.
    Вызывается при shutdown приложения.
    """
    await engine.dispose()
    logger.info("Database connections closed")
