"""
JWT Token Service для аутентификации.
Использует RS256 алгоритм с ротацией ключей.
Поддерживает multi-version JWT validation через database-backed keys.
"""

from datetime import datetime, timedelta, timezone
from typing import Dict, Optional, Tuple, List
from pathlib import Path
import logging

from jose import jwt, JWTError
from jose.exceptions import ExpiredSignatureError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.user import User
from app.models.service_account import ServiceAccount
from app.models.jwt_key import JWTKey

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
        Загрузка JWT ключей из файлов или прямого PEM содержимого.

        Поддерживает два варианта:
        1. File path - путь к PEM файлу (традиционный способ)
        2. Direct PEM content - полное PEM содержимое (для Kubernetes Secrets)

        Автоматически определяет тип по наличию "-----BEGIN" в начале строки.

        Raises:
            FileNotFoundError: Если ключи-файлы не найдены
            ValueError: Если ключи повреждены
        """
        try:
            # Загрузка private key
            private_key_value = settings.jwt.private_key_path

            if private_key_value.strip().startswith("-----BEGIN"):
                # Direct PEM content (из Kubernetes Secret или env variable)
                self._private_key = private_key_value
                logger.info("JWT private key loaded from direct PEM content")
            else:
                # File path (традиционный способ)
                private_key_path = Path(private_key_value)

                if not private_key_path.exists():
                    raise FileNotFoundError(f"Private key file not found: {private_key_path}")

                with open(private_key_path, "r") as f:
                    self._private_key = f.read()

                logger.info(f"JWT private key loaded from file: {private_key_path}")

            # Загрузка public key
            public_key_value = settings.jwt.public_key_path

            if public_key_value.strip().startswith("-----BEGIN"):
                # Direct PEM content (из Kubernetes Secret или env variable)
                self._public_key = public_key_value
                logger.info("JWT public key loaded from direct PEM content")
            else:
                # File path (традиционный способ)
                public_key_path = Path(public_key_value)

                if not public_key_path.exists():
                    raise FileNotFoundError(f"Public key file not found: {public_key_path}")

                with open(public_key_path, "r") as f:
                    self._public_key = f.read()

                logger.info(f"JWT public key loaded from file: {public_key_path}")

            logger.info("JWT keys loaded successfully")

        except Exception as e:
            logger.error(f"Failed to load JWT keys: {e}")
            raise

    def create_access_token(
        self,
        user: User,
        extra_claims: Optional[Dict] = None,
        session: Optional[Session] = None
    ) -> str:
        """
        Создание access токена для пользователя.

        Сначала пробует использовать latest active key из БД (если session передан),
        потом fallback на file-based ключ.

        Args:
            user: Пользователь для которого создается токен
            extra_claims: Дополнительные claims для токена
            session: Database session для получения latest key (опционально)

        Returns:
            str: Закодированный JWT токен

        Raises:
            ValueError: Если ни один ключ не доступен
        """
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

        # Попытка 1: Использование latest database key
        if session is not None:
            try:
                latest_key = JWTKey.get_latest_active_key(session)

                if latest_key:
                    token = jwt.encode(
                        claims,
                        latest_key.private_key,
                        algorithm=latest_key.algorithm
                    )
                    logger.info(
                        f"Created access token for user {user.username} using database key "
                        f"version {latest_key.version[:8]}... (expires: {expire})"
                    )
                    return token
                else:
                    logger.debug("No active keys in database, falling back to file-based key")

            except Exception as e:
                logger.warning(f"Failed to use database key: {e}, falling back to file-based key")

        # Попытка 2: Fallback на file-based ключ
        if self._private_key:
            token = jwt.encode(
                claims,
                self._private_key,
                algorithm=settings.jwt.algorithm
            )
            logger.info(
                f"Created access token for user {user.username} using file-based key "
                f"(expires: {expire})"
            )
            return token

        # Если ни один ключ не доступен
        raise ValueError("No private key available (database or file-based)")

    def create_refresh_token(self, user: User, session: Optional[Session] = None) -> str:
        """
        Создание refresh токена для пользователя.

        Сначала пробует использовать latest active key из БД (если session передан),
        потом fallback на file-based ключ.

        Args:
            user: Пользователь для которого создается токен
            session: Database session для получения latest key (опционально)

        Returns:
            str: Закодированный JWT refresh токен

        Raises:
            ValueError: Если ни один ключ не доступен
        """
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

        # Попытка 1: Использование latest database key
        if session is not None:
            try:
                latest_key = JWTKey.get_latest_active_key(session)

                if latest_key:
                    token = jwt.encode(
                        claims,
                        latest_key.private_key,
                        algorithm=latest_key.algorithm
                    )
                    logger.info(
                        f"Created refresh token for user {user.username} using database key "
                        f"version {latest_key.version[:8]}... (expires: {expire})"
                    )
                    return token
                else:
                    logger.debug("No active keys in database, falling back to file-based key")

            except Exception as e:
                logger.warning(f"Failed to use database key: {e}, falling back to file-based key")

        # Попытка 2: Fallback на file-based ключ
        if self._private_key:
            token = jwt.encode(
                claims,
                self._private_key,
                algorithm=settings.jwt.algorithm
            )
            logger.info(
                f"Created refresh token for user {user.username} using file-based key "
                f"(expires: {expire})"
            )
            return token

        # Если ни один ключ не доступен
        raise ValueError("No private key available (database or file-based)")

    def create_token_pair(self, user: User, session: Optional[Session] = None) -> Tuple[str, str]:
        """
        Создание пары access и refresh токенов.

        Args:
            user: Пользователь для которого создаются токены
            session: Database session для получения latest key (опционально)

        Returns:
            Tuple[str, str]: (access_token, refresh_token)
        """
        access_token = self.create_access_token(user, session=session)
        refresh_token = self.create_refresh_token(user, session=session)
        return access_token, refresh_token

    def create_token_from_data(
        self,
        data: Dict,
        expires_delta: timedelta,
        token_type: str = "access"
    ) -> str:
        """
        Generic метод создания токена с произвольными данными.

        Используется для Admin Users и Service Accounts, где нет legacy User model.

        Args:
            data: Payload для токена (должен включать 'sub', 'type', и т.д.)
            expires_delta: Время жизни токена
            token_type: Тип токена для логирования ("access" или "refresh")

        Returns:
            str: Закодированный JWT токен

        Raises:
            ValueError: Если ключ недоступен

        Examples:
            >>> token_data = {
            ...     "sub": "admin",
            ...     "type": "admin_user",
            ...     "role": "super_admin",
            ...     "jti": secrets.token_urlsafe(16)
            ... }
            >>> token = service.create_token_from_data(
            ...     data=token_data,
            ...     expires_delta=timedelta(minutes=30),
            ...     token_type="access"
            ... )
        """
        now = datetime.now(timezone.utc)
        expire = now + expires_delta

        # Создаем claims с timestamp полями
        claims = {
            **data,
            "iat": now,
            "exp": expire,
            "nbf": now
        }

        # Используем file-based ключ (для Admin Users DB keys не используются)
        if not self._private_key:
            raise ValueError("No private key available")

        token = jwt.encode(
            claims,
            self._private_key,
            algorithm=settings.jwt.algorithm
        )

        logger.info(
            f"Created {token_type} token for {data.get('sub')} "
            f"(type={data.get('type')}, expires: {expire})"
        )

        return token

    def decode_token(self, token: str, session: Optional[Session] = None) -> Dict:
        """
        Декодирование и валидация JWT токена с multi-version support.

        Сначала пробует валидацию всеми active keys из БД (если session передан),
        потом fallback на file-based ключ.

        Args:
            token: JWT токен для декодирования
            session: Database session для загрузки active keys (опционально)

        Returns:
            Dict: Payload токена

        Raises:
            JWTError: Если токен невалиден всеми ключами
            ExpiredSignatureError: Если токен истек
        """
        errors = []

        # Попытка 1: Multi-version validation через database keys
        if session is not None:
            try:
                active_keys = JWTKey.get_active_keys(session)

                if active_keys:
                    for key in active_keys:
                        try:
                            payload = jwt.decode(
                                token,
                                key.public_key,
                                algorithms=[key.algorithm]
                            )
                            logger.debug(
                                f"Token validated successfully with key version "
                                f"{key.version[:8]}... (created: {key.created_at})"
                            )
                            return payload

                        except ExpiredSignatureError:
                            # Токен истек - не пробуем другие ключи
                            logger.warning("Token has expired")
                            raise

                        except JWTError as e:
                            # Этот ключ не подошел - пробуем следующий
                            errors.append(f"Key {key.version[:8]}: {str(e)}")
                            continue

                    logger.debug(
                        f"Token validation failed with all {len(active_keys)} active database keys"
                    )
                else:
                    logger.debug("No active keys found in database, falling back to file-based key")

            except Exception as e:
                logger.warning(f"Failed to load keys from database: {e}")
                errors.append(f"Database: {str(e)}")

        # Попытка 2: Fallback на file-based ключ
        if self._public_key:
            try:
                payload = jwt.decode(
                    token,
                    self._public_key,
                    algorithms=[settings.jwt.algorithm]
                )
                logger.debug("Token validated successfully with file-based key")
                return payload

            except ExpiredSignatureError:
                logger.warning("Token has expired")
                raise

            except JWTError as e:
                errors.append(f"File-based key: {str(e)}")
        else:
            errors.append("File-based key: not loaded")

        # Если ни один ключ не подошел
        error_msg = f"Token validation failed with all available keys. Errors: {'; '.join(errors)}"
        logger.error(error_msg)
        raise JWTError(error_msg)

    def validate_token(
        self,
        token: str,
        token_type: str = "access",
        session: Optional[Session] = None
    ) -> Optional[Dict]:
        """
        Валидация токена с проверкой типа.

        Args:
            token: JWT токен для валидации
            token_type: Ожидаемый тип токена ("access" или "refresh")
            session: Database session для multi-version validation (опционально)

        Returns:
            Optional[Dict]: Payload токена если валиден, None если невалиден
        """
        try:
            payload = self.decode_token(token, session=session)

            # Проверяем тип токена
            if payload.get("type") != token_type:
                logger.warning(f"Invalid token type: expected {token_type}, got {payload.get('type')}")
                return None

            return payload

        except (JWTError, ExpiredSignatureError) as e:
            logger.debug(f"Token validation failed: {e}")
            return None

    def get_user_id_from_token(self, token: str, session: Optional[Session] = None) -> Optional[int]:
        """
        Извлечение user ID из токена.

        Args:
            token: JWT токен
            session: Database session для multi-version validation (опционально)

        Returns:
            Optional[int]: User ID если токен валиден, None иначе
        """
        payload = self.validate_token(token, session=session)
        if not payload:
            return None

        try:
            return int(payload.get("sub"))
        except (TypeError, ValueError):
            return None

    def refresh_access_token(
        self,
        refresh_token: str,
        user: User,
        session: Optional[Session] = None
    ) -> Optional[str]:
        """
        Обновление access токена используя refresh токен.

        Args:
            refresh_token: Валидный refresh токен
            user: Пользователь для которого создается новый access токен
            session: Database session для multi-version validation (опционально)

        Returns:
            Optional[str]: Новый access токен или None если refresh токен невалиден
        """
        payload = self.validate_token(refresh_token, token_type="refresh", session=session)
        if not payload:
            return None

        # Проверяем что refresh токен принадлежит этому пользователю
        token_user_id = payload.get("sub")
        if str(user.id) != token_user_id:
            logger.warning(f"Refresh token user mismatch: {token_user_id} != {user.id}")
            return None

        # Создаем новый access токен
        return self.create_access_token(user, session=session)

    # ========================================================================
    # SERVICE ACCOUNT TOKEN METHODS
    # ========================================================================

    def create_service_account_access_token(
        self,
        service_account: ServiceAccount,
        extra_claims: Optional[Dict] = None,
        session: Optional[Session] = None
    ) -> str:
        """
        Создание access токена для Service Account (OAuth 2.0 Client Credentials).

        Сначала пробует использовать latest active key из БД (если session передан),
        потом fallback на file-based ключ.

        Args:
            service_account: Service Account для которого создается токен
            extra_claims: Дополнительные claims для токена
            session: Database session для получения latest key (опционально)

        Returns:
            str: Закодированный JWT токен

        Raises:
            ValueError: Если ни один ключ не доступен
        """
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

        # Попытка 1: Использование latest database key
        if session is not None:
            try:
                latest_key = JWTKey.get_latest_active_key(session)

                if latest_key:
                    token = jwt.encode(
                        claims,
                        latest_key.private_key,
                        algorithm=latest_key.algorithm
                    )
                    logger.info(
                        f"Created access token for service account {service_account.client_id} "
                        f"using database key version {latest_key.version[:8]}... (expires: {expire})"
                    )
                    return token
                else:
                    logger.debug("No active keys in database, falling back to file-based key")

            except Exception as e:
                logger.warning(f"Failed to use database key: {e}, falling back to file-based key")

        # Попытка 2: Fallback на file-based ключ
        if self._private_key:
            token = jwt.encode(
                claims,
                self._private_key,
                algorithm=settings.jwt.algorithm
            )
            logger.info(
                f"Created access token for service account {service_account.client_id} "
                f"using file-based key (expires: {expire})"
            )
            return token

        # Если ни один ключ не доступен
        raise ValueError("No private key available (database or file-based)")

    def create_service_account_refresh_token(
        self,
        service_account: ServiceAccount,
        session: Optional[Session] = None
    ) -> str:
        """
        Создание refresh токена для Service Account.

        Сначала пробует использовать latest active key из БД (если session передан),
        потом fallback на file-based ключ.

        Args:
            service_account: Service Account для которого создается токен
            session: Database session для получения latest key (опционально)

        Returns:
            str: Закодированный JWT refresh токен

        Raises:
            ValueError: Если ни один ключ не доступен
        """
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

        # Попытка 1: Использование latest database key
        if session is not None:
            try:
                latest_key = JWTKey.get_latest_active_key(session)

                if latest_key:
                    token = jwt.encode(
                        claims,
                        latest_key.private_key,
                        algorithm=latest_key.algorithm
                    )
                    logger.info(
                        f"Created refresh token for service account {service_account.client_id} "
                        f"using database key version {latest_key.version[:8]}... (expires: {expire})"
                    )
                    return token
                else:
                    logger.debug("No active keys in database, falling back to file-based key")

            except Exception as e:
                logger.warning(f"Failed to use database key: {e}, falling back to file-based key")

        # Попытка 2: Fallback на file-based ключ
        if self._private_key:
            token = jwt.encode(
                claims,
                self._private_key,
                algorithm=settings.jwt.algorithm
            )
            logger.info(
                f"Created refresh token for service account {service_account.client_id} "
                f"using file-based key (expires: {expire})"
            )
            return token

        # Если ни один ключ не доступен
        raise ValueError("No private key available (database or file-based)")

    def create_service_account_token_pair(
        self,
        service_account: ServiceAccount,
        session: Optional[Session] = None
    ) -> Tuple[str, str]:
        """
        Создание пары access и refresh токенов для Service Account.

        Args:
            service_account: Service Account для которого создаются токены
            session: Database session для получения latest key (опционально)

        Returns:
            Tuple[str, str]: (access_token, refresh_token)
        """
        access_token = self.create_service_account_access_token(service_account, session=session)
        refresh_token = self.create_service_account_refresh_token(service_account, session=session)
        return access_token, refresh_token


# Глобальный экземпляр сервиса
token_service = TokenService()
