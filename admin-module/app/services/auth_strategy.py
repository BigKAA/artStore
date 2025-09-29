from abc import ABC, abstractmethod
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.user import User
from app.core.security import verify_password
from app import services


class AuthStrategy(ABC):
    """Абстрактный базовый класс для стратегий аутентификации."""

    @abstractmethod
    async def authenticate(self, db: AsyncSession, username: str, password: str) -> Optional[User]:
        """Аутентифицирует пользователя и возвращает его модель."""
        pass


class LocalAuthStrategy(AuthStrategy):
    """Стратегия аутентификации для локальных пользователей."""

    async def authenticate(self, db: AsyncSession, username: str, password: str) -> Optional[User]:
        user = await services.user.get_by_username(db, username=username)
        if not user:
            return None
        if not verify_password(password, user.hashed_password):
            return None
        return user

from typing import List

# ... (существующие импорты)

# ... (AuthStrategy, LocalAuthStrategy)

class LdapAuthStrategy(AuthStrategy):
    async def authenticate(self, db: AsyncSession, username: str, password: str) -> Optional[User]:
        # TODO: Реализовать логику аутентификации через LDAP
        raise NotImplementedError("LDAP аутентификация еще не реализована.")

class CompositeAuthStrategy(AuthStrategy):
    """Композитная стратегия, которая пробует несколько стратегий по очереди."""

    def __init__(self, strategies: List[AuthStrategy]):
        self.strategies = strategies

    async def authenticate(self, db: AsyncSession, username: str, password: str) -> Optional[User]:
        for strategy in self.strategies:
            try:
                user = await strategy.authenticate(db, username, password)
                if user:
                    return user
            except NotImplementedError:
                continue  # Пропускаем нереализованные стратегии
        return None

def get_auth_strategy(providers: List[str]) -> AuthStrategy:
    """Фабричная функция для получения композитной стратегии."""
    strategies: List[AuthStrategy] = []
    for provider in providers:
        if provider == "local":
            strategies.append(LocalAuthStrategy())
        elif provider == "ldap":
            strategies.append(LdapAuthStrategy())
        else:
            raise NotImplementedError(f"Провайдер аутентификации '{provider}' не поддерживается.")
    return CompositeAuthStrategy(strategies)