"""
Query Module - Database Layer.

Async PostgreSQL connection management 7 SQLAlchemy.
A?>;L7C5BAO 4;O:
- Full-Text Search 8=45:A>2 (GIN)
- 5H8@>20=85 <5B040==KE D09;>2
- %@0=5=85 AB0B8AB8:8 ?>8A:0
"""

import logging
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    AsyncEngine,
    create_async_engine,
    async_sessionmaker
)
from sqlalchemy import text
from sqlalchemy.orm import declarative_base
from sqlalchemy.pool import NullPool, AsyncAdaptedQueuePool

from app.core.config import settings
from app.core.exceptions import DatabaseConnectionException

logger = logging.getLogger(__name__)

# Declarative Base 4;O <>45;59
Base = declarative_base()

# Global engine 8 session maker
_engine: AsyncEngine | None = None
_async_session_maker: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    """
    >;CG8BL async SQLAlchemy engine.

    Returns:
        AsyncEngine: 0AB@>5==K9 async engine

    Raises:
        DatabaseConnectionException: A;8 engine =5 8=8F80;878@>20=
    """
    global _engine

    if _engine is None:
        raise DatabaseConnectionException("Database engine not initialized. Call init_db() first.")

    return _engine


def get_session_maker() -> async_sessionmaker[AsyncSession]:
    """
    >;CG8BL session maker 4;O A>740=8O async sessions.

    Returns:
        async_sessionmaker: Session factory

    Raises:
        DatabaseConnectionException: A;8 session maker =5 8=8F80;878@>20=
    """
    global _async_session_maker

    if _async_session_maker is None:
        raise DatabaseConnectionException("Session maker not initialized. Call init_db() first.")

    return _async_session_maker


async def init_db() -> None:
    """
    =8F80;870F8O database engine 8 session maker.

    !>7405B connection pool 8 ?@>25@O5B ?>4:;NG5=85 : .
    K7K205BAO ?@8 AB0@B5 ?@8;>65=8O 2 lifespan context.
    """
    global _engine, _async_session_maker

    try:
        # !>740=85 async engine
        _engine = create_async_engine(
            settings.database.database_url,
            echo=settings.database.echo,
            pool_size=settings.database.pool_size,
            max_overflow=settings.database.max_overflow,
            pool_timeout=settings.database.pool_timeout,
            poolclass=AsyncAdaptedQueuePool,
            # 06=>: 8A?>;L7C5< asyncpg driver
            # postgresql+asyncpg://user:pass@host:port/db
        )

        # !>740=85 session maker
        _async_session_maker = async_sessionmaker(
            _engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autocommit=False,
            autoflush=False,
        )

        # @>25@:0 ?>4:;NG5=8O
        async with _engine.begin() as conn:
            await conn.execute(text("SELECT 1"))

        logger.info(
            "Database initialized successfully",
            extra={
                "database_url": settings.database.database_url.split("@")[1],  # 57 ?0@>;O
                "pool_size": settings.database.pool_size,
                "max_overflow": settings.database.max_overflow
            }
        )

    except Exception as e:
        logger.error(
            "Failed to initialize database",
            extra={"error": str(e)}
        )
        raise DatabaseConnectionException(f"Database initialization failed: {str(e)}")


async def close_db() -> None:
    """
    0:@KB85 database connections.

    0:@K205B 2A5 active connections 8 >A2>1>6405B @5AC@AK.
    K7K205BAO ?@8 >AB0=>2:5 ?@8;>65=8O 2 lifespan context.
    """
    global _engine, _async_session_maker

    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _async_session_maker = None

        logger.info("Database connections closed")


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency 4;O ?>;CG5=8O async database session 2 FastAPI.

    Yields:
        AsyncSession: Async database session

    @8<5@K:
        >>> @app.get("/search")
        >>> async def search_files(
        ...     db: AsyncSession = Depends(get_db_session)
        ... ):
        ...     result = await db.execute(select(FileMetadata))
        ...     return result.scalars().all()
    """
    session_maker = get_session_maker()

    async with session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def check_db_health() -> bool:
    """
    @>25@:0 health database A>548=5=8O.

    Returns:
        bool: True 5A;8  4>ABC?=0

    A?>;L7C5BAO 2 /health/ready endpoint.
    """
    try:
        engine = get_engine()

        async with engine.begin() as conn:
            await conn.execute(text("SELECT 1"))

        return True

    except Exception as e:
        logger.warning(
            "Database health check failed",
            extra={"error": str(e)}
        )
        return False
