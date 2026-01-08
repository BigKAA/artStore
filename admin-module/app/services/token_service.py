"""
JWT Token Service для аутентификации.
Использует RS256 алгоритм с ротацией ключей.
Поддерживает multi-version JWT validation через database-backed keys.

Sprint: JWT Hot-Reload Implementation (2026-01-08)
- Интеграция с JWTKeyManager для автоматического hot-reload ключей
- Zero-downtime rotation через file watching
"""

from datetime import datetime, timedelta, timezone
from typing import Dict, Optional, Tuple, List
from pathlib import Path
import logging
import secrets

from jose import jwt, JWTError
from jose.exceptions import ExpiredSignatureError
from sqlalchemy.orm import Session

from app.core.config import settings
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
    - Hot-reload ключей через JWTKeyManager (Sprint: JWT Hot-Reload)
    """

    def __init__(self):
        """
        Инициализация сервиса токенов с hot-reload support.

        Sprint: JWT Hot-Reload Implementation (2026-01-08)
        - Удален метод _load_keys()
        - Использует JWTKeyManager singleton для доступа к ключам
        - Автоматический hot-reload ключей без перезапуска
        """
        from app.core.jwt_key_manager import get_jwt_key_manager

        self._key_manager = get_jwt_key_manager()


    # ПРИМЕЧАНИЕ: Старые методы create_access_token, create_refresh_token, create_token_pair
    # для User модели удалены в Sprint 21. Используйте вместо них:
    # - create_service_account_access_token() для Service Accounts
    # - create_token_from_data() для Admin Users

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

        # Используем JWTKeyManager для получения ключа (Sprint: JWT Hot-Reload)
        private_key = self._key_manager.get_private_key_sync()

        token = jwt.encode(
            claims,
            private_key,
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

        # Попытка 2: Fallback на file-based ключ (Sprint: JWT Hot-Reload)
        try:
            public_key = self._key_manager.get_public_key_sync()

            payload = jwt.decode(
                token,
                public_key,
                algorithms=[settings.jwt.algorithm]
            )
            logger.debug("Token validated successfully with file-based key")
            return payload

        except ExpiredSignatureError:
            logger.warning("Token has expired")
            raise

        except JWTError as e:
            errors.append(f"File-based key: {str(e)}")
        except ValueError as e:
            errors.append(f"File-based key: {str(e)}")

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

    # ПРИМЕЧАНИЕ: Метод refresh_access_token для User модели удален в Sprint 21.
    # Используйте create_token_from_data() для Admin Users вместо этого.

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

        # UNIFIED JWT PAYLOAD - Sprint 20
        # Изменения: type "access" → "service_account", добавлен jti
        claims = {
            "sub": str(service_account.id),  # Subject - UUID Service Account
            "type": "service_account",  # ✅ ИЗМЕНЕНО: унифицированный тип токена
            "role": service_account.role.value,
            "name": service_account.name,
            "jti": secrets.token_urlsafe(16),  # ✅ НОВОЕ: JWT ID для token revocation
            "client_id": service_account.client_id,
            "rate_limit": service_account.rate_limit,
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

        # UNIFIED JWT PAYLOAD - Sprint 20 (refresh token)
        claims = {
            "sub": str(service_account.id),
            "type": "service_account",  # ✅ ИЗМЕНЕНО: унифицированный тип
            "role": service_account.role.value,  # ✅ ДОБАВЛЕНО: для консистентности
            "name": service_account.name,  # ✅ ДОБАВЛЕНО: display name
            "jti": secrets.token_urlsafe(16),  # ✅ ДОБАВЛЕНО: JWT ID
            "client_id": service_account.client_id,
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
