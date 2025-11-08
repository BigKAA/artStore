"""
Database dependencies для FastAPI endpoints.

Provides database session injection и utility functions.
"""

from typing import Generator
from sqlalchemy.orm import Session
from fastapi import Depends

from app.db.base import get_db

# Re-export get_db для удобства
get_database = get_db


def get_db_session() -> Generator[Session, None, None]:
    """
    Alias for get_db - provides database session dependency.

    Usage:
        ```python
        from app.api.deps.database import get_db_session

        @app.get("/files")
        async def list_files(db: Session = Depends(get_db_session)):
            ...
        ```
    """
    yield from get_db()
