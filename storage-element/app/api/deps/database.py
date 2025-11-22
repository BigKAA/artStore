"""
FastAPI Dependencies для работы с базой данных.

Управление database sessions для endpoints.
"""

from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import AsyncSessionLocal


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Получить database session для endpoint.

    FastAPI dependency для автоматического управления сессиями.
    Сессия закрывается после завершения request.

    Yields:
        AsyncSession: Async database session

    Примеры:
        >>> @app.get("/files")
        >>> async def list_files(db: Annotated[AsyncSession, Depends(get_db)]):
        ...     result = await db.execute(select(FileMetadata))
        ...     return result.scalars().all()
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()
