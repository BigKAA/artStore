"""
Admin Authentication Service для аутентификации администраторов Admin UI.

Использует login/password аутентификацию с JWT токенами (RS256).
Отдельно от Service Account аутентификации (OAuth 2.0 Client Credentials).
"""

from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple
import secrets
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from passlib.context import CryptContext

from app.models.admin_user import AdminUser, AdminRole
from app.services.token_service import TokenService
from app.core.password_policy import PasswordPolicy, PasswordValidator, PasswordGenerator
from app.services.audit_service import AuditService
from app.core.database import get_sync_session

logger = logging.getLogger(__name__)

# Bcrypt context для хеширования паролей (work factor 12)
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class AdminAuthenticationError(Exception):
    """Базовое исключение для ошибок аутентификации администраторов."""
    pass


class InvalidCredentialsError(AdminAuthenticationError):
    """Неверные учетные данные (username или password)."""
    pass


class AccountLockedError(AdminAuthenticationError):
    """Аккаунт заблокирован из-за множественных неудачных попыток."""
    pass


class AccountDisabledError(AdminAuthenticationError):
    """Аккаунт отключен администратором."""
    pass


class PasswordInHistoryError(AdminAuthenticationError):
    """Пароль уже использовался ранее (в истории)."""
    pass


class AdminAuthService:
    """
    Сервис для аутентификации администраторов Admin UI.

    Функции:
    - Login с username/password
    - JWT token generation (access + refresh)
    - Token validation
    - Password change
    - Account locking после неудачных попыток
    - Password history tracking
    """

    def __init__(self):
        """Инициализация сервиса аутентификации."""
        self.token_service = TokenService()
        self.password_policy = PasswordPolicy(
            min_length=8,  # Для Admin UI можем использовать 8 символов (более user-friendly)
            require_uppercase=True,
            require_lowercase=True,
            require_digits=True,
            require_special=False,  # Необязательны для Admin UI
            max_age_days=90,
            history_size=5
        )
        self.password_validator = PasswordValidator(self.password_policy)
        self.password_generator = PasswordGenerator(self.password_policy)
        self.audit_service = AuditService()

    @staticmethod
    def hash_password(password: str) -> str:
        """
        Хеширование пароля с использованием bcrypt (work factor 12).

        Args:
            password: Пароль в plaintext

        Returns:
            Bcrypt хеш пароля
        """
        return pwd_context.hash(password)

    @staticmethod
    def verify_password(plain_password: str, hashed_password: str) -> bool:
        """
        Проверка пароля против bcrypt хеша.

        Args:
            plain_password: Пароль в plaintext
            hashed_password: Bcrypt хеш пароля

        Returns:
            True если пароль верный, False иначе
        """
        return pwd_context.verify(plain_password, hashed_password)

    async def authenticate(
        self,
        db: AsyncSession,
        username: str,
        password: str
    ) -> Tuple[str, str]:
        """
        Аутентификация администратора по username и password.

        Процесс:
        1. Найти пользователя по username
        2. Проверить что аккаунт активен и не заблокирован
        3. Проверить пароль
        4. Сбросить счетчик неудачных попыток при успехе
        5. Увеличить счетчик при неудаче (блокировка после 5 попыток)
        6. Сгенерировать JWT access и refresh токены
        7. Обновить last_login_at
        8. Записать в audit log

        Args:
            db: Database session
            username: Имя пользователя
            password: Пароль

        Returns:
            Tuple[access_token, refresh_token]

        Raises:
            InvalidCredentialsError: Неверные учетные данные
            AccountLockedError: Аккаунт заблокирован
            AccountDisabledError: Аккаунт отключен
        """
        # Найти пользователя по username
        result = await db.execute(
            select(AdminUser).where(AdminUser.username == username.lower())
        )
        admin_user = result.scalar_one_or_none()

        if not admin_user:
            logger.warning(f"Login attempt with non-existent username: {username}")
            raise InvalidCredentialsError("Invalid username or password")

        # Проверка что аккаунт активен
        if not admin_user.enabled:
            logger.warning(f"Login attempt for disabled account: {username}")
            # Audit logging (sync session)
            try:
                sync_session = next(get_sync_session())
                try:
                    self.audit_service.log_admin_login_attempt(
                        sync_session, admin_user.id, success=False, reason="Account disabled"
                    )
                finally:
                    sync_session.close()
            except Exception as e:
                logger.error(f"Audit logging failed: {e}")
            raise AccountDisabledError("Account is disabled")

        # Проверка блокировки аккаунта
        if admin_user.is_locked():
            logger.warning(f"Login attempt for locked account: {username}")
            # Audit logging (sync session)
            try:
                sync_session = next(get_sync_session())
                try:
                    self.audit_service.log_admin_login_attempt(
                        sync_session, admin_user.id, success=False, reason="Account locked"
                    )
                finally:
                    sync_session.close()
            except Exception as e:
                logger.error(f"Audit logging failed: {e}")
            raise AccountLockedError(
                f"Account is locked until {admin_user.locked_until.isoformat()}"
            )

        # Проверка пароля
        if not self.verify_password(password, admin_user.password_hash):
            logger.warning(f"Invalid password for username: {username}")

            # Увеличиваем счетчик неудачных попыток
            admin_user.increment_login_attempts(lock_duration_minutes=15)
            await db.commit()

            # Audit logging (sync session)
            try:
                sync_session = next(get_sync_session())
                try:
                    self.audit_service.log_admin_login_attempt(
                        sync_session, admin_user.id, success=False, reason="Invalid password"
                    )
                finally:
                    sync_session.close()
            except Exception as e:
                logger.error(f"Audit logging failed: {e}")

            raise InvalidCredentialsError("Invalid username or password")

        # Успешная аутентификация
        logger.info(f"Successful login for admin: {username}")

        # Сброс счетчика неудачных попыток
        admin_user.reset_login_attempts()

        # Обновление last_login_at
        admin_user.last_login_at = datetime.now(timezone.utc)

        await db.commit()
        await db.refresh(admin_user)

        # Генерация JWT токенов
        access_token, refresh_token = self._create_tokens(admin_user)

        # Audit log (sync session)
        try:
            sync_session = next(get_sync_session())
            try:
                self.audit_service.log_admin_login_attempt(
                    sync_session, admin_user.id, success=True, reason="Successful login"
                )
            finally:
                sync_session.close()
        except Exception as e:
            logger.error(f"Audit logging failed: {e}")

        return access_token, refresh_token

    async def refresh_token(
        self,
        db: AsyncSession,
        refresh_token: str
    ) -> Tuple[str, str]:
        """
        Обновление access token через refresh token.

        Args:
            db: Database session
            refresh_token: JWT refresh token

        Returns:
            Tuple[new_access_token, new_refresh_token]

        Raises:
            InvalidCredentialsError: Невалидный refresh token
        """
        try:
            # Декодирование refresh token
            payload = self.token_service.decode_token(refresh_token)

            # Проверка типа токена
            if payload.get("type") != "admin_user":
                raise InvalidCredentialsError("Invalid token type")

            username = payload.get("sub")
            if not username:
                raise InvalidCredentialsError("Invalid token payload")

            # Найти администратора
            result = await db.execute(
                select(AdminUser).where(AdminUser.username == username)
            )
            admin_user = result.scalar_one_or_none()

            if not admin_user:
                raise InvalidCredentialsError("Admin user not found")

            if not admin_user.can_login():
                raise AccountDisabledError("Account is disabled or locked")

            # Генерация новых токенов
            access_token, new_refresh_token = self._create_tokens(admin_user)

            logger.info(f"Token refreshed for admin: {username}")

            return access_token, new_refresh_token

        except Exception as e:
            logger.error(f"Token refresh failed: {e}")
            raise InvalidCredentialsError("Invalid refresh token")

    async def change_password(
        self,
        db: AsyncSession,
        admin_user: AdminUser,
        current_password: str,
        new_password: str
    ) -> None:
        """
        Смена пароля администратора.

        Процесс:
        1. Проверить текущий пароль
        2. Валидировать новый пароль (strength policy)
        3. Проверить что новый пароль не в истории
        4. Добавить текущий пароль в историю
        5. Обновить password_hash
        6. Обновить password_changed_at
        7. Audit log

        Args:
            db: Database session
            admin_user: Объект AdminUser
            current_password: Текущий пароль
            new_password: Новый пароль

        Raises:
            InvalidCredentialsError: Неверный текущий пароль
            PasswordInHistoryError: Пароль уже использовался
            ValueError: Пароль не соответствует политике
        """
        # Проверка текущего пароля
        if not self.verify_password(current_password, admin_user.password_hash):
            logger.warning(f"Invalid current password for admin: {admin_user.username}")
            raise InvalidCredentialsError("Invalid current password")

        # Валидация нового пароля
        is_valid, errors = self.password_validator.validate(new_password)
        if not is_valid:
            raise ValueError(f"Password policy violation: {', '.join(errors)}")

        # Хеширование нового пароля
        new_password_hash = self.hash_password(new_password)

        # Проверка истории паролей
        if admin_user.is_password_in_history(new_password_hash):
            raise PasswordInHistoryError(
                f"Password was used recently. Cannot reuse last {self.password_policy.history_size} passwords."
            )

        # Добавление текущего пароля в историю
        admin_user.add_password_to_history(
            admin_user.password_hash,
            max_history=self.password_policy.history_size
        )

        # Обновление пароля
        admin_user.password_hash = new_password_hash
        admin_user.password_changed_at = datetime.now(timezone.utc)

        await db.commit()

        logger.info(f"Password changed for admin: {admin_user.username}")

        # Audit log (sync session)
        try:
            sync_session = next(get_sync_session())
            try:
                self.audit_service.log_password_change(
                    sync_session, admin_user.id, "Admin password changed successfully"
                )
            finally:
                sync_session.close()
        except Exception as e:
            logger.error(f"Audit logging failed: {e}")

    async def get_admin_by_username(
        self,
        db: AsyncSession,
        username: str
    ) -> Optional[AdminUser]:
        """
        Получение администратора по username.

        Args:
            db: Database session
            username: Имя пользователя

        Returns:
            AdminUser объект или None
        """
        result = await db.execute(
            select(AdminUser).where(AdminUser.username == username.lower())
        )
        return result.scalar_one_or_none()

    def _create_tokens(self, admin_user: AdminUser) -> Tuple[str, str]:
        """
        Создание JWT access и refresh токенов для администратора.

        Args:
            admin_user: Объект AdminUser

        Returns:
            Tuple[access_token, refresh_token]
        """
        # UNIFIED JWT PAYLOAD - Sprint 20
        # Добавлены поля name и client_id для унификации с Service Account токенами
        token_data = {
            "sub": admin_user.username,
            "type": "admin_user",  # Отличается от "service_account"
            "role": admin_user.role.value,
            "name": admin_user.username,  # ✅ НОВОЕ: display name для логов и UI
            "jti": secrets.token_urlsafe(16),  # JWT ID для token revocation (будущее)
            "client_id": f"user_{admin_user.username}"  # ✅ НОВОЕ: унифицированный client_id
        }

        # Создание access token (30 минут)
        access_token = self.token_service.create_token_from_data(
            data=token_data,
            expires_delta=timedelta(minutes=30),
            token_type="access"
        )

        # Создание refresh token (7 дней)
        refresh_token = self.token_service.create_token_from_data(
            data=token_data,
            expires_delta=timedelta(days=7),
            token_type="refresh"
        )

        return access_token, refresh_token

    def generate_random_password(self, length: int = 16) -> str:
        """
        Генерация криптографически случайного пароля.

        Args:
            length: Длина пароля (default: 16)

        Returns:
            Случайный пароль соответствующий password policy
        """
        return self.password_generator.generate(length=length)
