"""
Настройка асинхронного подключения к PostgreSQL.
"""
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import declarative_base

# Базовый класс для моделей
Base = declarative_base()

# Глобальные переменные для engine и session_maker
engine = None
async_session_maker = None


def init_db_engine(database_url: str, pool_size: int = 10, max_overflow: int = 20, echo: bool = False):
    """
    Инициализирует async engine и session maker.

    Args:
        database_url: URL подключения к базе данных
        pool_size: Количество постоянных соединений
        max_overflow: Дополнительные соединения при пиковой нагрузке
        echo: Логирование SQL запросов
    """
    global engine, async_session_maker

    # Создание async engine
    engine = create_async_engine(
        database_url,
        pool_size=pool_size,
        max_overflow=max_overflow,
        echo=echo,  # Логирование SQL запросов
        future=True,
        pool_pre_ping=True,  # Проверка соединения перед использованием
    )

    # Создание session maker
    async_session_maker = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,  # Объекты доступны после commit
        autocommit=False,
        autoflush=False,
    )


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency для получения DB session в FastAPI endpoints.

    Usage:
        @app.get("/users/")
        async def get_users(db: AsyncSession = Depends(get_db)):
            ...

    Yields:
        AsyncSession для выполнения запросов
    """
    if async_session_maker is None:
        raise RuntimeError("Database engine not initialized. Call init_db_engine() first.")

    async with async_session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db():
    """
    Инициализация БД: создание всех таблиц.
    Вызывается при старте приложения.

    Note: В production используйте Alembic миграции вместо этой функции.
    """
    if engine is None:
        raise RuntimeError("Database engine not initialized. Call init_db_engine() first.")

    async with engine.begin() as conn:
        # Создание всех таблиц
        await conn.run_sync(Base.metadata.create_all)


async def close_db():
    """
    Закрытие соединений с БД.
    Вызывается при остановке приложения.
    """
    if engine is not None:
        await engine.dispose()
