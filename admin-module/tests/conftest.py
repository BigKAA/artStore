"""
Pytest fixtures для тестирования Admin Module.
"""

import pytest
import asyncio
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.pool import NullPool
import sys
from pathlib import Path

# Добавляем путь к app для импортов
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.models import Base
from app.core.config import settings


# Настройка event loop для async тестов
@pytest.fixture(scope="session")
def event_loop():
    """Создание event loop для всей сессии тестирования."""
    policy = asyncio.get_event_loop_policy()
    loop = policy.new_event_loop()
    yield loop
    loop.close()


# Фикстура для тестовой базы данных
@pytest.fixture(scope="session")
async def test_engine():
    """
    Создание тестового database engine.
    Использует отдельную тестовую базу данных.
    """
    # URL для тестовой БД
    test_db_url = settings.database.url.replace(
        settings.database.database,
        f"{settings.database.database}_test"
    )

    engine = create_async_engine(
        test_db_url,
        echo=False,
        poolclass=NullPool,  # Без pooling для тестов
    )

    # Создаем все таблицы
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    # Удаляем все таблицы после тестов
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()


@pytest.fixture
async def db_session(test_engine) -> AsyncGenerator[AsyncSession, None]:
    """
    Фикстура для получения database session в тестах.
    Каждый тест получает свою сессию с rollback после завершения.
    """
    async_session = async_sessionmaker(
        test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )

    async with async_session() as session:
        async with session.begin():
            yield session
            await session.rollback()


@pytest.fixture
async def client():
    """
    Фикстура для FastAPI TestClient.
    Используется для тестирования API endpoints.
    """
    from fastapi.testclient import TestClient
    from app.main import app

    with TestClient(app) as test_client:
        yield test_client
