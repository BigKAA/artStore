"""
Модель пользователя системы.
"""
import uuid

from sqlalchemy import Boolean, Column, DateTime, String, Text
from sqlalchemy.sql import func

from app.db.session import Base


def generate_uuid():
    """Генерация UUID v4 для ID пользователя"""
    return str(uuid.uuid4())


class User(Base):
    """
    Модель пользователя.

    Атрибуты:
        id: Уникальный идентификатор (UUID)
        login: Логин пользователя (уникальный)
        email: Email (уникальный)
        hashed_password: Bcrypt хеш пароля
        last_name: Фамилия
        first_name: Имя
        middle_name: Отчество (опционально)
        is_active: Активен ли пользователь
        is_admin: Является ли администратором
        is_system: Системный пользователь (защищен от удаления)
        description: Описание пользователя
        created_at: Дата создания
        updated_at: Дата последнего обновления
    """

    __tablename__ = "users"

    # Первичный ключ
    id = Column(String(36), primary_key=True, default=generate_uuid, index=True)

    # Основные данные
    login = Column(String(100), unique=True, nullable=False, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)

    # ФИО
    last_name = Column(String(100), nullable=False)
    first_name = Column(String(100), nullable=False)
    middle_name = Column(String(100), nullable=True)

    # Статусы
    is_active = Column(Boolean, default=True, nullable=False)
    is_admin = Column(Boolean, default=False, nullable=False)
    is_system = Column(Boolean, default=False, nullable=False)

    # Дополнительная информация
    description = Column(Text, nullable=True)

    # Метаданные
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    def __repr__(self):
        return f"<User(id={self.id}, login={self.login}, is_admin={self.is_admin})>"

    @property
    def full_name(self) -> str:
        """
        Возвращает полное имя пользователя (Фамилия Имя Отчество).
        """
        if self.middle_name:
            return f"{self.last_name} {self.first_name} {self.middle_name}"
        return f"{self.last_name} {self.first_name}"

    @property
    def is_protected(self) -> bool:
        """
        Проверка, защищен ли пользователь от изменений.
        Системный пользователь не может быть удален или лишен прав администратора.
        """
        return self.is_system
