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


# Список таблиц, необходимых для работы Admin Module
REQUIRED_TABLES = [
    "admin_users",
    "storage_elements",
    "service_accounts",
    "jwt_keys",
    "audit_logs"
]


async def check_db_tables() -> tuple[bool, list[str]]:
    """
    Проверка наличия всех необходимых таблиц в базе данных.
    Используется в readiness health checks для проверки версии схемы.

    Returns:
        tuple: (all_present, missing_tables)
            - all_present: True если все таблицы существуют
            - missing_tables: Список отсутствующих таблиц

    Example:
        ok, missing = await check_db_tables()
        if not ok:
            logger.error(f"Missing tables: {missing}")
    """
    try:
        async with engine.begin() as conn:
            result = await conn.execute(text(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'public'"
            ))
            existing_tables = {row[0] for row in result.fetchall()}
            missing_tables = [t for t in REQUIRED_TABLES if t not in existing_tables]
            return len(missing_tables) == 0, missing_tables
    except Exception as e:
        logger.error(f"Failed to check database tables: {e}")
        return False, REQUIRED_TABLES


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


async def create_standalone_async_session() -> AsyncSession:
    """
    Создание standalone async session для background задач.

    ВАЖНО: Эта функция создает новый engine и session для использования
    в отдельном event loop (например, в APScheduler background jobs).

    НЕ ИСПОЛЬЗОВАТЬ в FastAPI endpoints - там используйте get_db().

    Returns:
        AsyncSession: Новая async session с собственным engine

    Example:
        async def background_task():
            session = await create_standalone_async_session()
            try:
                # Работа с сессией
                result = await session.execute(select(Model))
            finally:
                await session.close()
    """
    # Создаем отдельный engine для этого event loop
    standalone_engine = create_async_engine(
        settings.database.url,
        echo=False,  # Отключаем echo для background jobs
        pool_pre_ping=True,
        pool_size=2,  # Маленький пул для background jobs
        max_overflow=1,
        connect_args={"ssl": False},
    )

    # Создаем session maker
    standalone_session_maker = async_sessionmaker(
        standalone_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )

    return standalone_session_maker()


async def check_db_connection_standalone() -> bool:
    """
    Standalone версия проверки подключения к базе данных.

    Создаёт собственный engine для использования в отдельном event loop
    (например, в APScheduler background jobs с asyncio.run()).

    ВАЖНО: НЕ ИСПОЛЬЗОВАТЬ в FastAPI endpoints - там используйте check_db_connection().

    Returns:
        bool: True если подключение работает, False иначе
    """
    standalone_engine = None
    try:
        standalone_engine = create_async_engine(
            settings.database.url,
            echo=False,
            pool_pre_ping=True,
            pool_size=1,
            max_overflow=0,
            connect_args={"ssl": False},
        )
        async with standalone_engine.begin() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception as e:
        logger.error(f"Standalone database connection check failed: {e}")
        return False
    finally:
        if standalone_engine:
            await standalone_engine.dispose()


async def check_db_tables_standalone() -> tuple[bool, list[str]]:
    """
    Standalone версия проверки наличия всех необходимых таблиц.

    Создаёт собственный engine для использования в отдельном event loop
    (например, в APScheduler background jobs с asyncio.run()).

    ВАЖНО: НЕ ИСПОЛЬЗОВАТЬ в FastAPI endpoints - там используйте check_db_tables().

    Returns:
        tuple: (all_present, missing_tables)
            - all_present: True если все таблицы существуют
            - missing_tables: Список отсутствующих таблиц
    """
    standalone_engine = None
    try:
        standalone_engine = create_async_engine(
            settings.database.url,
            echo=False,
            pool_pre_ping=True,
            pool_size=1,
            max_overflow=0,
            connect_args={"ssl": False},
        )
        async with standalone_engine.begin() as conn:
            result = await conn.execute(text(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'public'"
            ))
            existing_tables = {row[0] for row in result.fetchall()}
            missing_tables = [t for t in REQUIRED_TABLES if t not in existing_tables]
            return len(missing_tables) == 0, missing_tables
    except Exception as e:
        logger.error(f"Standalone failed to check database tables: {e}")
        return False, REQUIRED_TABLES
    finally:
        if standalone_engine:
            await standalone_engine.dispose()
