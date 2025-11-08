"""
SQLAlchemy base configuration для Storage Element.

Provides database engine, session factory, and base model class.
"""

from sqlalchemy import create_engine, MetaData
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from sqlalchemy.pool import NullPool, QueuePool
from typing import Generator
import logging

from app.core.config import get_config

logger = logging.getLogger(__name__)

# SQLAlchemy metadata with naming convention for constraints
metadata = MetaData(
    naming_convention={
        "ix": "ix_%(column_0_label)s",
        "uq": "uq_%(table_name)s_%(column_0_name)s",
        "ck": "ck_%(table_name)s_%(constraint_name)s",
        "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
        "pk": "pk_%(table_name)s"
    }
)

# Declarative base for all models
Base = declarative_base(metadata=metadata)


def get_engine(pool_size: int = 5, max_overflow: int = 10, pool_pre_ping: bool = True):
    """
    Create database engine with connection pooling.

    Args:
        pool_size: Size of connection pool
        max_overflow: Max overflow connections
        pool_pre_ping: Enable connection health checks

    Returns:
        Engine: SQLAlchemy engine
    """
    config = get_config()

    engine = create_engine(
        config.database.connection_url,
        poolclass=QueuePool,
        pool_size=pool_size,
        max_overflow=max_overflow,
        pool_pre_ping=pool_pre_ping,  # Проверка соединений перед использованием
        pool_recycle=3600,  # Переподключение каждый час
        echo=config.debug,  # SQL logging в debug mode
    )

    logger.info(
        "Database engine created",
        host=config.database.host,
        database=config.database.database,
        pool_size=pool_size
    )

    return engine


def get_session_factory(engine=None):
    """
    Create session factory for database sessions.

    Args:
        engine: Optional custom engine (uses default if None)

    Returns:
        sessionmaker: Session factory
    """
    if engine is None:
        engine = get_engine()

    SessionLocal = sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=engine
    )

    return SessionLocal


# Global engine and session factory
_engine = None
_SessionLocal = None


def init_db():
    """
    Initialize database engine and session factory.

    Creates all tables if they don't exist.
    """
    global _engine, _SessionLocal

    _engine = get_engine()
    _SessionLocal = get_session_factory(_engine)

    # Create all tables
    Base.metadata.create_all(bind=_engine)

    logger.info("Database initialized, tables created")


def get_db() -> Generator[Session, None, None]:
    """
    Dependency для FastAPI endpoints - provides database session.

    Yields:
        Session: Database session

    Examples:
        ```python
        from fastapi import Depends
        from app.db.base import get_db

        @app.get("/files")
        async def list_files(db: Session = Depends(get_db)):
            files = db.query(FileMetadata).all()
            return files
        ```
    """
    if _SessionLocal is None:
        init_db()

    db = _SessionLocal()
    try:
        yield db
    finally:
        db.close()


def close_db():
    """
    Close database engine and dispose of connection pool.

    Should be called on application shutdown.
    """
    global _engine

    if _engine:
        _engine.dispose()
        logger.info("Database engine disposed")
