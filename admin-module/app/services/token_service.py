"""
JWT Token Service для аутентификации.
Использует RS256 алгоритм с ротацией ключей.
"""

from datetime import datetime, timedelta, timezone
from typing import Dict, Optional, Tuple
from pathlib import Path
import logging

from jose import jwt, JWTError
from jose.exceptions import ExpiredSignatureError

from app.core.config import settings
from app.models.user import User
from app.models.service_account import ServiceAccount

logger = logging.getLogger(__name__)


class TokenService:
    """
    Сервис для работы с JWT токенами.

    Функции:
    - Генерация access и refresh токенов
    - Валидация токенов
    - Декодирование payload
    - Поддержка ротации ключей
    """

    def __init__(self):
        """Инициализация сервиса токенов."""
        self._private_key: Optional[str] = None
        self._public_key: Optional[str] = None
        self._load_keys()

    def _load_keys(self) -> None:
        """
        Загрузка JWT ключей из файлов.

        Raises:
            FileNotFoundError: Если ключи не найдены
            ValueError: Если ключи повреждены
        """
        try:
            private_key_path = Path(settings.jwt.private_key_path)
            public_key_path = Path(settings.jwt.public_key_path)

            if not private_key_path.exists():
                raise FileNotFoundError(f"Private key not found: {private_key_path}")

            if not public_key_path.exists():
                raise FileNotFoundError(f"Public key not found: {public_key_path}")

            with open(private_key_path, "r") as f:
                self._private_key = f.read()

            with open(public_key_path, "r") as f:
                self._public_key = f.read()

            logger.info("JWT keys loaded successfully")

        except Exception as e:
            logger.error(f"Failed to load JWT keys: {e}")
            raise

    def create_access_token(self, user: User, extra_claims: Optional[Dict] = None) -> str:
        """
        Создание access токена для пользователя.

        Args:
            user: Пользователь для которого создается токен
            extra_claims: Дополнительные claims для токена

        Returns:
            str: Закодированный JWT токен

        Raises:
            ValueError: Если приватный ключ не загружен
        """
        if not self._private_key:
            raise ValueError("Private key not loaded")

        now = datetime.now(timezone.utc)
        expire = now + timedelta(minutes=settings.jwt.access_token_expire_minutes)

        # Базовые claims
        claims = {
            "sub": str(user.id),  # Subject - ID пользователя
            "username": user.username,
            "email": user.email,
            "role": user.role.value,
            "type": "access",
            "iat": now,  # Issued At
            "exp": expire,  # Expiration Time
            "nbf": now,  # Not Before
        }

        # Добавляем дополнительные claims если есть
        if extra_claims:
            claims.update(extra_claims)

        # Кодируем токен
        token = jwt.encode(
            claims,
            self._private_key,
            algorithm=settings.jwt.algorithm
        )

        logger.info(f"Created access token for user {user.username} (expires: {expire})")
        return token

    def create_refresh_token(self, user: User) -> str:
        """
        Создание refresh токена для пользователя.

        Args:
            user: Пользователь для которого создается токен

        Returns:
            str: Закодированный JWT refresh токен

        Raises:
            ValueError: Если приватный ключ не загружен
        """
        if not self._private_key:
            raise ValueError("Private key not loaded")

        now = datetime.now(timezone.utc)
        expire = now + timedelta(days=settings.jwt.refresh_token_expire_days)

        claims = {
            "sub": str(user.id),
            "username": user.username,
            "type": "refresh",
            "iat": now,
            "exp": expire,
            "nbf": now,
        }

        token = jwt.encode(
            claims,
            self._private_key,
            algorithm=settings.jwt.algorithm
        )

        logger.info(f"Created refresh token for user {user.username} (expires: {expire})")
        return token

    def create_token_pair(self, user: User) -> Tuple[str, str]:
        """
        Создание пары access и refresh токенов.

        Args:
            user: Пользователь для которого создаются токены

        Returns:
            Tuple[str, str]: (access_token, refresh_token)
        """
        access_token = self.create_access_token(user)
        refresh_token = self.create_refresh_token(user)
        return access_token, refresh_token

    def decode_token(self, token: str) -> Dict:
        """
        Декодирование и валидация JWT токена.

        Args:
            token: JWT токен для декодирования

        Returns:
            Dict: Payload токена

        Raises:
            JWTError: Если токен невалиден
            ExpiredSignatureError: Если токен истек
        """
        if not self._public_key:
            raise ValueError("Public key not loaded")

        try:
            payload = jwt.decode(
                token,
                self._public_key,
                algorithms=[settings.jwt.algorithm]
            )
            return payload

        except ExpiredSignatureError:
            logger.warning("Token has expired")
            raise

        except JWTError as e:
            logger.error(f"Token validation failed: {e}")
            raise

    def validate_token(self, token: str, token_type: str = "access") -> Optional[Dict]:
        """
        Валидация токена с проверкой типа.

        Args:
            token: JWT токен для валидации
            token_type: Ожидаемый тип токена ("access" или "refresh")

        Returns:
            Optional[Dict]: Payload токена если валиден, None если невалиден
        """
        try:
            payload = self.decode_token(token)

            # Проверяем тип токена
            if payload.get("type") != token_type:
                logger.warning(f"Invalid token type: expected {token_type}, got {payload.get('type')}")
                return None

            return payload

        except (JWTError, ExpiredSignatureError) as e:
            logger.debug(f"Token validation failed: {e}")
            return None

    def get_user_id_from_token(self, token: str) -> Optional[int]:
        """
        Извлечение user ID из токена.

        Args:
            token: JWT токен

        Returns:
            Optional[int]: User ID если токен валиден, None иначе
        """
        payload = self.validate_token(token)
        if not payload:
            return None

        try:
            return int(payload.get("sub"))
        except (TypeError, ValueError):
            return None

    def refresh_access_token(self, refresh_token: str, user: User) -> Optional[str]:
        """
        Обновление access токена используя refresh токен.

        Args:
            refresh_token: Валидный refresh токен
            user: Пользователь для которого создается новый access токен

        Returns:
            Optional[str]: Новый access токен или None если refresh токен невалиден
        """
        payload = self.validate_token(refresh_token, token_type="refresh")
        if not payload:
            return None

        # Проверяем что refresh токен принадлежит этому пользователю
        token_user_id = payload.get("sub")
        if str(user.id) != token_user_id:
            logger.warning(f"Refresh token user mismatch: {token_user_id} != {user.id}")
            return None

        # Создаем новый access токен
        return self.create_access_token(user)

    # ========================================================================
    # SERVICE ACCOUNT TOKEN METHODS
    # ========================================================================

    def create_service_account_access_token(
        self,
        service_account: ServiceAccount,
        extra_claims: Optional[Dict] = None
    ) -> str:
        """
        Создание access токена для Service Account (OAuth 2.0 Client Credentials).

        Args:
            service_account: Service Account для которого создается токен
            extra_claims: Дополнительные claims для токена

        Returns:
            str: Закодированный JWT токен

        Raises:
            ValueError: Если приватный ключ не загружен
        """
        if not self._private_key:
            raise ValueError("Private key not loaded")

        now = datetime.now(timezone.utc)
        expire = now + timedelta(minutes=settings.jwt.access_token_expire_minutes)

        # Базовые claims для Service Account
        claims = {
            "sub": str(service_account.id),  # Subject - UUID Service Account
            "client_id": service_account.client_id,
            "name": service_account.name,
            "role": service_account.role.value,
            "rate_limit": service_account.rate_limit,
            "type": "access",
            "iat": now,  # Issued At
            "exp": expire,  # Expiration Time
            "nbf": now,  # Not Before
        }

        # Добавляем дополнительные claims если есть
        if extra_claims:
            claims.update(extra_claims)

        # Кодируем токен
        token = jwt.encode(
            claims,
            self._private_key,
            algorithm=settings.jwt.algorithm
        )

        logger.info(
            f"Created access token for service account {service_account.client_id} "
            f"(expires: {expire})"
        )
        return token

    def create_service_account_refresh_token(self, service_account: ServiceAccount) -> str:
        """
        Создание refresh токена для Service Account.

        Args:
            service_account: Service Account для которого создается токен

        Returns:
            str: Закодированный JWT refresh токен

        Raises:
            ValueError: Если приватный ключ не загружен
        """
        if not self._private_key:
            raise ValueError("Private key not loaded")

        now = datetime.now(timezone.utc)
        expire = now + timedelta(days=settings.jwt.refresh_token_expire_days)

        claims = {
            "sub": str(service_account.id),
            "client_id": service_account.client_id,
            "type": "refresh",
            "iat": now,
            "exp": expire,
            "nbf": now,
        }

        token = jwt.encode(
            claims,
            self._private_key,
            algorithm=settings.jwt.algorithm
        )

        logger.info(
            f"Created refresh token for service account {service_account.client_id} "
            f"(expires: {expire})"
        )
        return token

    def create_service_account_token_pair(
        self,
        service_account: ServiceAccount
    ) -> Tuple[str, str]:
        """
        Создание пары access и refresh токенов для Service Account.

        Args:
            service_account: Service Account для которого создаются токены

        Returns:
            Tuple[str, str]: (access_token, refresh_token)
        """
        access_token = self.create_service_account_access_token(service_account)
        refresh_token = self.create_service_account_refresh_token(service_account)
        return access_token, refresh_token


# Глобальный экземпляр сервиса
token_service = TokenService()
