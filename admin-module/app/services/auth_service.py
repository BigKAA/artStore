"""
Сервис аутентификации.
Координирует аутентификацию через local/LDAP/OAuth2.
"""
from typing import Optional, Dict, Tuple
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.db.models.user import User
from app.core.security import (
    verify_password,
    create_access_token,
    create_refresh_token,
    decode_token
)
from app.services.user_service import user_service
from app.services.ldap_service import ldap_service
from app.config import settings
from app.utils.logger import get_logger

logger = get_logger(__name__)


class AuthService:
    """
    Сервис аутентификации пользователей.
    Поддерживает каскадную аутентификацию через несколько источников.
    """

    async def authenticate_local(
        self,
        db: AsyncSession,
        username: str,
        password: str
    ) -> Optional[User]:
        """
        Аутентификация через локальную БД.

        Args:
            db: Database session
            username: Имя пользователя
            password: Пароль

        Returns:
            User если аутентификация успешна, иначе None
        """
        # Получаем пользователя
        user = await user_service.get_user_by_username(db, username)

        if not user:
            logger.debug(f"Пользователь не найден: {username}")
            return None

        # Проверяем, что пользователь из локальной БД
        if user.auth_provider != "local":
            logger.debug(f"Пользователь не из локальной БД: {username} (provider: {user.auth_provider})")
            return None

        # Проверяем пароль
        if not verify_password(password, user.hashed_password):
            logger.warning(f"Неверный пароль для пользователя: {username}")
            return None

        # Проверяем активность
        if not user.is_active:
            logger.warning(f"Попытка входа неактивного пользователя: {username}")
            return None

        logger.info(f"Успешная локальная аутентификация: {username}")
        return user

    async def authenticate_ldap(
        self,
        db: AsyncSession,
        username: str,
        password: str
    ) -> Optional[User]:
        """
        Аутентификация через LDAP.
        Автоматически создает/обновляет пользователя в локальной БД.

        Args:
            db: Database session
            username: Имя пользователя
            password: Пароль

        Returns:
            User если успешно, иначе None
        """
        if not settings.features.ldap_enabled:
            return None

        # Аутентификация через LDAP
        success, ldap_user_data = ldap_service.authenticate(username, password)

        if not success:
            return None

        # Поиск или создание пользователя в локальной БД
        user = await user_service.get_user_by_username(db, username)

        if user:
            # Обновление существующего пользователя
            user.email = ldap_user_data['email']
            user.full_name = ldap_user_data['full_name']
            user.is_admin = ldap_user_data['is_admin']
            user.auth_provider = 'ldap'
            user.last_synced_at = datetime.utcnow()
            user.updated_at = datetime.utcnow()
            await db.commit()
            await db.refresh(user)
            logger.info(f"Обновлен LDAP пользователь: {username}")
        else:
            # Создание нового пользователя
            if not settings.auth.ldap.auto_create_users:
                logger.warning(f"Автосоздание LDAP пользователей отключено: {username}")
                return None

            user = User(
                username=username,
                email=ldap_user_data['email'],
                full_name=ldap_user_data['full_name'],
                hashed_password="",  # Пароль не храним для LDAP пользователей
                is_active=True,
                is_admin=ldap_user_data['is_admin'],
                is_system=False,
                auth_provider='ldap',
                last_synced_at=datetime.utcnow()
            )
            db.add(user)
            await db.commit()
            await db.refresh(user)
            logger.info(f"Создан новый LDAP пользователь: {username}")

        return user

    async def authenticate(
        self,
        db: AsyncSession,
        username: str,
        password: str
    ) -> Tuple[Optional[User], str]:
        """
        Универсальная аутентификация.
        Последовательно пытается: local → LDAP.

        Args:
            db: Database session
            username: Имя пользователя
            password: Пароль

        Returns:
            Tuple (User, auth_method) или (None, "")
        """
        # Попытка 1: Локальная аутентификация
        user = await self.authenticate_local(db, username, password)
        if user:
            return user, "local"

        # Попытка 2: LDAP аутентификация
        user = await self.authenticate_ldap(db, username, password)
        if user:
            return user, "ldap"

        logger.warning(f"Неудачная попытка аутентификации: {username}")
        return None, ""

    def create_tokens(self, user: User) -> Dict[str, str]:
        """
        Создает access и refresh токены для пользователя.

        Args:
            user: Пользователь

        Returns:
            Dict с токенами
        """
        # Payload для токенов
        token_data = {
            "sub": user.id,
            "username": user.username,
            "is_admin": user.is_admin
        }

        # Создание токенов
        access_token = create_access_token(token_data)
        refresh_token = create_refresh_token({"sub": user.id})

        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
            "expires_in": settings.auth.jwt.access_token_expire_minutes * 60
        }

    async def refresh_access_token(
        self,
        db: AsyncSession,
        refresh_token: str
    ) -> Optional[Dict[str, str]]:
        """
        Обновляет access токен используя refresh токен.

        Args:
            db: Database session
            refresh_token: Refresh токен

        Returns:
            Dict с новыми токенами или None если refresh токен невалиден
        """
        try:
            # Декодируем refresh токен
            payload = decode_token(refresh_token)

            # Проверяем тип токена
            if payload.get("type") != "refresh":
                logger.warning("Попытка использовать не refresh токен")
                return None

            # Получаем пользователя
            user_id = payload.get("sub")
            user = await user_service.get_user_by_id(db, user_id)

            if not user or not user.is_active:
                logger.warning(f"Пользователь не найден или неактивен: {user_id}")
                return None

            # Создаем новые токены
            return self.create_tokens(user)

        except Exception as e:
            logger.error(f"Ошибка обновления токена: {e}")
            return None

    async def validate_token(self, token: str) -> Optional[Dict]:
        """
        Валидирует токен и возвращает информацию о пользователе.

        Args:
            token: JWT токен

        Returns:
            Dict с информацией о пользователе или None
        """
        try:
            payload = decode_token(token)

            # Проверяем тип токена (должен быть access)
            if payload.get("type") != "access":
                return None

            return {
                "valid": True,
                "user_id": payload.get("sub"),
                "username": payload.get("username"),
                "is_admin": payload.get("is_admin"),
                "expires_at": datetime.fromtimestamp(payload.get("exp")).isoformat()
            }

        except Exception as e:
            logger.debug(f"Невалидный токен: {e}")
            return None


# Глобальный экземпляр сервиса
auth_service = AuthService()
