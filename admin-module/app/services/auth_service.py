"""
Authentication Service для управления аутентификацией пользователей.
Поддерживает локальную аутентификацию через OAuth 2.0 Client Credentials.
"""

from datetime import datetime, timedelta
from typing import Optional, Tuple
import logging
import bcrypt

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User, UserStatus
from app.core.config import settings

logger = logging.getLogger(__name__)


class AuthService:
    """
    Сервис аутентификации пользователей.

    Функции:
    - Локальная аутентификация (username + password)
    - Управление failed login attempts
    - Lockout mechanism
    - Password hashing и verification
    """

    @staticmethod
    def hash_password(password: str) -> str:
        """
        Хеширование пароля используя bcrypt.

        Args:
            password: Пароль в открытом виде

        Returns:
            str: Хеш пароля
        """
        # Преобразуем пароль в bytes и хешируем
        password_bytes = password.encode('utf-8')
        salt = bcrypt.gensalt()
        hashed = bcrypt.hashpw(password_bytes, salt)
        # Возвращаем как строку
        return hashed.decode('utf-8')

    @staticmethod
    def verify_password(plain_password: str, hashed_password: str) -> bool:
        """
        Проверка пароля против хеша.

        Args:
            plain_password: Пароль в открытом виде
            hashed_password: Хеш пароля

        Returns:
            bool: True если пароль верен
        """
        try:
            password_bytes = plain_password.encode('utf-8')
            hashed_bytes = hashed_password.encode('utf-8')
            return bcrypt.checkpw(password_bytes, hashed_bytes)
        except Exception as e:
            logger.error(f"Password verification error: {e}")
            return False

    async def authenticate_local(
        self,
        db: AsyncSession,
        username: str,
        password: str
    ) -> Optional[User]:
        """
        Локальная аутентификация пользователя.

        Args:
            db: Database session
            username: Имя пользователя или email
            password: Пароль

        Returns:
            Optional[User]: Пользователь если аутентификация успешна, None иначе
        """
        # Ищем пользователя по username или email
        stmt = select(User).where(
            (User.username == username) | (User.email == username)
        )
        result = await db.execute(stmt)
        user = result.scalar_one_or_none()

        if not user:
            logger.warning(f"User not found: {username}")
            return None

        # Проверяем возможность входа
        if not user.can_login():
            logger.warning(f"User cannot login: {username} (status: {user.status})")

            # Обновляем failed attempts если аккаунт не заблокирован
            if user.status != UserStatus.LOCKED:
                user.increment_failed_attempts()
                await db.commit()

            return None

        # Проверяем пароль
        if not user.hashed_password:
            logger.error(f"User has no password hash: {username}")
            return None

        if not self.verify_password(password, user.hashed_password):
            logger.warning(f"Invalid password for user: {username}")

            # Увеличиваем счетчик неудачных попыток
            user.increment_failed_attempts()
            await db.commit()

            return None

        # Успешная аутентификация - сбрасываем failed attempts
        user.reset_failed_attempts()
        user.last_login = datetime.utcnow()
        await db.commit()

        logger.info(f"User authenticated successfully: {username}")
        return user

    async def authenticate(
        self,
        db: AsyncSession,
        username: str,
        password: str
    ) -> Optional[User]:
        """
        Аутентификация пользователя (только локальная).

        Args:
            db: Database session
            username: Имя пользователя
            password: Пароль

        Returns:
            Optional[User]: Пользователь если аутентификация успешна, None иначе
        """
        return await self.authenticate_local(db, username, password)

    async def get_user_by_id(self, db: AsyncSession, user_id: int) -> Optional[User]:
        """
        Получение пользователя по ID.

        Args:
            db: Database session
            user_id: ID пользователя

        Returns:
            Optional[User]: Пользователь или None
        """
        stmt = select(User).where(User.id == user_id)
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_user_by_username(self, db: AsyncSession, username: str) -> Optional[User]:
        """
        Получение пользователя по username.

        Args:
            db: Database session
            username: Имя пользователя

        Returns:
            Optional[User]: Пользователь или None
        """
        stmt = select(User).where(User.username == username)
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    async def create_password_reset_token(
        self,
        db: AsyncSession,
        email: str
    ) -> Optional[str]:
        """
        Создание токена для сброса пароля.

        Args:
            db: Database session
            email: Email пользователя

        Returns:
            Optional[str]: Reset token или None если пользователь не найден
        """
        # Ищем пользователя по email
        stmt = select(User).where(User.email == email)
        result = await db.execute(stmt)
        user = result.scalar_one_or_none()

        if not user:
            logger.warning(f"Password reset requested for unknown email: {email}")
            # Не раскрываем что пользователь не найден (security)
            return None

        # TODO: Создать и сохранить reset token в Redis
        # TODO: Отправить email с токеном
        # Пока возвращаем заглушку
        logger.info(f"Password reset token created for user: {user.username}")
        return "reset_token_placeholder"

    async def reset_password(
        self,
        db: AsyncSession,
        reset_token: str,
        new_password: str
    ) -> bool:
        """
        Сброс пароля используя reset token.

        Args:
            db: Database session
            reset_token: Token сброса пароля
            new_password: Новый пароль

        Returns:
            bool: True если пароль успешно изменен
        """
        # TODO: Валидация reset token из Redis
        # TODO: Получение user_id из токена
        # Пока возвращаем заглушку
        logger.info("Password reset attempted with token")
        return False


# Глобальный экземпляр сервиса
auth_service = AuthService()
