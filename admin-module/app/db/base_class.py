from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import MetaData

class Base(DeclarativeBase):
    """
    Базовый класс для всех моделей SQLAlchemy.
    """
    metadata = MetaData()
