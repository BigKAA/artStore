"""
Базовая модель для всех моделей SQLAlchemy.
"""

from datetime import datetime
from sqlalchemy import Column, DateTime
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from typing import Any


class Base(DeclarativeBase):
    """Базовый класс для всех моделей."""

    pass


class TimestampMixin:
    """Mixin для добавления created_at и updated_at полей."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        nullable=False,
        comment="Дата и время создания записи"
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
        comment="Дата и время последнего обновления записи"
    )
