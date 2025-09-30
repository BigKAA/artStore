"""
Сервис для управления пользователями.
"""
from typing import List, Optional
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_password_hash, verify_password
from app.db.models.user import User
from app.schemas.user import UserCreate, UserUpdate


class UserService:
    """
    Сервис для работы с пользователями.

    Реализует бизнес-логику управления пользователями:
    - Создание и удаление пользователей
    - Обновление данных пользователей
    - Смена паролей
    - Поиск пользователей
    """

    @staticmethod
    async def create_user(
        db: AsyncSession,
        user_data: UserCreate,
        is_system: bool = False
    ) -> User:
        """
        Создание нового пользователя.

        Args:
            db: Асинхронная сессия БД
            user_data: Данные для создания пользователя
            is_system: Флаг системного пользователя

        Returns:
            Созданный пользователь

        Raises:
            ValueError: Если пользователь с таким login или email уже существует
        """
        # Проверка уникальности login
        existing_user = await UserService.get_user_by_login(db, user_data.login)
        if existing_user:
            raise ValueError(f"Пользователь с login '{user_data.login}' уже существует")

        # Проверка уникальности email
        existing_user = await UserService.get_user_by_email(db, user_data.email)
        if existing_user:
            raise ValueError(f"Пользователь с email '{user_data.email}' уже существует")

        # Валидация пароля (минимум 8 символов)
        if len(user_data.password) < 8:
            raise ValueError("Пароль должен содержать минимум 8 символов")

        # Создание пользователя
        hashed_password = get_password_hash(user_data.password)

        user = User(
            id=str(uuid4()),
            login=user_data.login,
            email=user_data.email,
            hashed_password=hashed_password,
            last_name=user_data.last_name,
            first_name=user_data.first_name,
            middle_name=user_data.middle_name,
            is_admin=user_data.is_admin,
            is_active=True,
            is_system=is_system,
            description=user_data.description
        )

        db.add(user)
        await db.flush()
        await db.refresh(user)

        return user

    @staticmethod
    async def get_user_by_id(
        db: AsyncSession,
        user_id: str
    ) -> Optional[User]:
        """
        Получение пользователя по ID.

        Args:
            db: Асинхронная сессия БД
            user_id: UUID пользователя

        Returns:
            Пользователь или None
        """
        result = await db.execute(
            select(User).where(User.id == user_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_user_by_login(
        db: AsyncSession,
        login: str
    ) -> Optional[User]:
        """
        Получение пользователя по login.

        Args:
            db: Асинхронная сессия БД
            login: Логин пользователя

        Returns:
            Пользователь или None
        """
        result = await db.execute(
            select(User).where(User.login == login)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_user_by_email(
        db: AsyncSession,
        email: str
    ) -> Optional[User]:
        """
        Получение пользователя по email.

        Args:
            db: Асинхронная сессия БД
            email: Email пользователя

        Returns:
            Пользователь или None
        """
        result = await db.execute(
            select(User).where(User.email == email)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def update_user(
        db: AsyncSession,
        user_id: str,
        user_data: UserUpdate
    ) -> User:
        """
        Обновление данных пользователя.

        Args:
            db: Асинхронная сессия БД
            user_id: UUID пользователя
            user_data: Данные для обновления

        Returns:
            Обновленный пользователь

        Raises:
            ValueError: Если пользователь не найден или является системным
        """
        user = await UserService.get_user_by_id(db, user_id)
        if not user:
            raise ValueError(f"Пользователь с ID '{user_id}' не найден")

        # Защита системного пользователя
        if user.is_system:
            raise ValueError("Невозможно изменить системного пользователя")

        # Обновление полей (только те, что переданы)
        update_data = user_data.model_dump(exclude_unset=True)

        # Проверка уникальности login, если он изменяется
        if "login" in update_data and update_data["login"] != user.login:
            existing_user = await UserService.get_user_by_login(db, update_data["login"])
            if existing_user:
                raise ValueError(f"Пользователь с login '{update_data['login']}' уже существует")

        # Проверка уникальности email, если он изменяется
        if "email" in update_data and update_data["email"] != user.email:
            existing_user = await UserService.get_user_by_email(db, update_data["email"])
            if existing_user:
                raise ValueError(f"Пользователь с email '{update_data['email']}' уже существует")

        # Применение изменений
        for field, value in update_data.items():
            setattr(user, field, value)

        await db.flush()
        await db.refresh(user)

        return user

    @staticmethod
    async def delete_user(
        db: AsyncSession,
        user_id: str
    ) -> None:
        """
        Удаление пользователя.

        Args:
            db: Асинхронная сессия БД
            user_id: UUID пользователя

        Raises:
            ValueError: Если пользователь не найден или является системным
        """
        user = await UserService.get_user_by_id(db, user_id)
        if not user:
            raise ValueError(f"Пользователь с ID '{user_id}' не найден")

        # Защита системного пользователя
        if user.is_system:
            raise ValueError("Невозможно удалить системного пользователя")

        await db.delete(user)
        await db.flush()

    @staticmethod
    async def change_password(
        db: AsyncSession,
        user_id: str,
        old_password: str,
        new_password: str
    ) -> User:
        """
        Смена пароля пользователя.

        Args:
            db: Асинхронная сессия БД
            user_id: UUID пользователя
            old_password: Текущий пароль
            new_password: Новый пароль

        Returns:
            Обновленный пользователь

        Raises:
            ValueError: Если пользователь не найден, старый пароль неверен
                       или новый пароль не соответствует требованиям
        """
        user = await UserService.get_user_by_id(db, user_id)
        if not user:
            raise ValueError(f"Пользователь с ID '{user_id}' не найден")

        # Проверка старого пароля
        if not verify_password(old_password, user.hashed_password):
            raise ValueError("Неверный текущий пароль")

        # Валидация нового пароля
        if len(new_password) < 8:
            raise ValueError("Новый пароль должен содержать минимум 8 символов")

        if new_password == old_password:
            raise ValueError("Новый пароль не должен совпадать со старым")

        # Обновление пароля
        user.hashed_password = get_password_hash(new_password)

        await db.flush()
        await db.refresh(user)

        return user

    @staticmethod
    async def list_users(
        db: AsyncSession,
        skip: int = 0,
        limit: int = 20,
        is_active: Optional[bool] = None,
        is_admin: Optional[bool] = None
    ) -> tuple[List[User], int]:
        """
        Получение списка пользователей с пагинацией.

        Args:
            db: Асинхронная сессия БД
            skip: Количество пропускаемых записей
            limit: Максимальное количество записей
            is_active: Фильтр по активности (опционально)
            is_admin: Фильтр по роли администратора (опционально)

        Returns:
            Кортеж (список пользователей, общее количество)
        """
        # Базовый запрос
        query = select(User)

        # Применение фильтров
        if is_active is not None:
            query = query.where(User.is_active == is_active)

        if is_admin is not None:
            query = query.where(User.is_admin == is_admin)

        # Подсчет общего количества
        count_result = await db.execute(
            select(func.count()).select_from(query.subquery())
        )
        total = count_result.scalar_one()

        # Получение списка с пагинацией
        query = query.offset(skip).limit(limit).order_by(User.created_at.desc())
        result = await db.execute(query)
        users = result.scalars().all()

        return list(users), total
