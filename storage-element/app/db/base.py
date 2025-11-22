"""
Database base classes для SQLAlchemy ORM.

Определяет базовый класс для всех моделей.
"""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """
    Базовый класс для всех ORM моделей.

    Все модели должны наследоваться от этого класса.
    """
    pass
