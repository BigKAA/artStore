"""
Service Account Service для управления Service Accounts.

Поддерживает CRUD операции, генерацию client credentials,
управление ротацией secrets и OAuth 2.0 аутентификацию.

Sprint 16 Phase 1: Enhanced Password Security
- Password Policy integration для сильных секретов
- Password history tracking для предотвращения reuse
- Password expiration enforcement
"""

from datetime import datetime, timedelta, timezone
from typing import Optional, List
from uuid import UUID
import logging
import bcrypt
import secrets
import string

from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.service_account import (
    ServiceAccount,
    ServiceAccountRole,
    ServiceAccountStatus
)
from app.core.config import settings
from app.core.password_policy import (
    PasswordPolicy,
    PasswordValidator,
    PasswordGenerator,
    PasswordHistory
)

logger = logging.getLogger(__name__)


class ServiceAccountService:
    """
    Сервис для управления Service Accounts.

    Функции:
    - CRUD операции (create, read, update, delete)
    - Генерация secure client_secret с Password Policy enforcement
    - client_secret hashing и verification (bcrypt)
    - Password history tracking для предотвращения reuse
    - Автоматическая ротация secrets
    - OAuth 2.0 Client Credentials authentication

    Sprint 16 Phase 1: Enhanced Security
    - PasswordGenerator для криптографически стойких секретов
    - PasswordValidator для policy compliance проверки
    - PasswordHistory для предотвращения reuse
    """

    def __init__(self):
        """Инициализация сервиса с Password Policy infrastructure."""
        # Создание password policy из настроек
        self.password_policy = PasswordPolicy(
            min_length=settings.password.min_length,
            require_uppercase=settings.password.require_uppercase,
            require_lowercase=settings.password.require_lowercase,
            require_digits=settings.password.require_digits,
            require_special=settings.password.require_special,
            max_age_days=settings.password.max_age_days,
            history_size=settings.password.history_size
        )

        # Инициализация password components
        self.password_validator = PasswordValidator(self.password_policy)
        self.password_generator = PasswordGenerator(self.password_policy)
        self.password_history = PasswordHistory(self.password_policy)

    def generate_client_secret(self, length: Optional[int] = None) -> str:
        """
        Генерация безопасного client_secret согласно Password Policy.

        Sprint 16 Phase 1: Cryptographically secure generation с policy enforcement

        Args:
            length: Длина секрета (default: policy.min_length + 4)

        Returns:
            str: Криптографически стойкий случайный секрет

        Example:
            >>> secret = service.generate_client_secret()
            >>> len(secret) >= 12  # policy minimum
            True
        """
        # Используем PasswordGenerator для cryptographically secure generation
        if length is None:
            length = self.password_policy.min_length + 4  # 16 символов по умолчанию

        return self.password_generator.generate(length)

    @staticmethod
    def hash_secret(secret: str) -> str:
        """
        Хеширование client_secret используя bcrypt.

        Args:
            secret: Secret в открытом виде

        Returns:
            str: Bcrypt хеш секрета
        """
        secret_bytes = secret.encode('utf-8')
        salt = bcrypt.gensalt(rounds=12)  # Increased rounds for security
        hashed = bcrypt.hashpw(secret_bytes, salt)
        return hashed.decode('utf-8')

    @staticmethod
    def verify_secret(plain_secret: str, hashed_secret: str) -> bool:
        """
        Проверка client_secret против хеша.

        Args:
            plain_secret: Secret в открытом виде
            hashed_secret: Bcrypt хеш секрета

        Returns:
            bool: True если секрет верен
        """
        try:
            secret_bytes = plain_secret.encode('utf-8')
            hashed_bytes = hashed_secret.encode('utf-8')
            return bcrypt.checkpw(secret_bytes, hashed_bytes)
        except Exception as e:
            logger.error(f"Secret verification error: {e}")
            return False

    async def create_service_account(
        self,
        db: AsyncSession,
        name: str,
        role: ServiceAccountRole,
        description: Optional[str] = None,
        rate_limit: int = 100,
        environment: str = "prod",
        is_system: bool = False
    ) -> tuple[ServiceAccount, str]:
        """
        Создание нового Service Account.

        Args:
            db: Database session
            name: Название Service Account
            role: Роль (ADMIN, USER, AUDITOR, READONLY)
            description: Описание назначения
            rate_limit: Лимит запросов в минуту
            environment: Окружение (prod, staging, dev)
            is_system: Флаг системного аккаунта

        Returns:
            tuple[ServiceAccount, str]: (Service Account объект, plain client_secret)

        Raises:
            ValueError: Если Service Account с таким именем уже существует
        """
        # Проверка уникальности имени
        stmt = select(ServiceAccount).where(ServiceAccount.name == name)
        result = await db.execute(stmt)
        existing = result.scalar_one_or_none()

        if existing:
            raise ValueError(f"Service Account with name '{name}' already exists")

        # Генерация client_id и client_secret
        client_id = ServiceAccount.generate_client_id(name, environment)
        client_secret = self.generate_client_secret()
        client_secret_hash = self.hash_secret(client_secret)

        # Расчет срока истечения secret (90 дней)
        secret_expires_at = ServiceAccount.calculate_secret_expiry(days=90)

        # Создание Service Account (Sprint 16 Phase 1: password history initialization)
        service_account = ServiceAccount(
            name=name,
            description=description,
            client_id=client_id,
            client_secret_hash=client_secret_hash,
            secret_history=[],  # Пустая история при создании
            secret_changed_at=datetime.now(timezone.utc),  # Initial password set
            role=role,
            status=ServiceAccountStatus.ACTIVE,
            is_system=is_system,
            rate_limit=rate_limit,
            secret_expires_at=secret_expires_at,
        )

        db.add(service_account)
        await db.commit()
        await db.refresh(service_account)

        logger.info(
            f"Created Service Account: {name} "
            f"(client_id={client_id}, role={role}, rate_limit={rate_limit})"
        )

        # Возвращаем plain secret ТОЛЬКО при создании (единственный раз)
        return service_account, client_secret

    async def get_by_id(
        self,
        db: AsyncSession,
        service_account_id: UUID
    ) -> Optional[ServiceAccount]:
        """
        Получение Service Account по ID.

        Args:
            db: Database session
            service_account_id: UUID Service Account

        Returns:
            Optional[ServiceAccount]: Service Account если найден
        """
        stmt = select(ServiceAccount).where(ServiceAccount.id == service_account_id)
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_client_id(
        self,
        db: AsyncSession,
        client_id: str
    ) -> Optional[ServiceAccount]:
        """
        Получение Service Account по client_id.

        Args:
            db: Database session
            client_id: Client ID для OAuth 2.0

        Returns:
            Optional[ServiceAccount]: Service Account если найден
        """
        stmt = select(ServiceAccount).where(ServiceAccount.client_id == client_id)
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_name(
        self,
        db: AsyncSession,
        name: str
    ) -> Optional[ServiceAccount]:
        """
        Получение Service Account по имени.

        Args:
            db: Database session
            name: Название Service Account

        Returns:
            Optional[ServiceAccount]: Service Account если найден
        """
        stmt = select(ServiceAccount).where(ServiceAccount.name == name)
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    async def list_service_accounts(
        self,
        db: AsyncSession,
        status: Optional[ServiceAccountStatus] = None,
        role: Optional[ServiceAccountRole] = None,
        skip: int = 0,
        limit: int = 100
    ) -> List[ServiceAccount]:
        """
        Список Service Accounts с фильтрацией и пагинацией.

        Args:
            db: Database session
            status: Фильтр по статусу (optional)
            role: Фильтр по роли (optional)
            skip: Offset для пагинации
            limit: Лимит записей

        Returns:
            List[ServiceAccount]: Список Service Accounts
        """
        stmt = select(ServiceAccount)

        if status:
            stmt = stmt.where(ServiceAccount.status == status)
        if role:
            stmt = stmt.where(ServiceAccount.role == role)

        stmt = stmt.offset(skip).limit(limit).order_by(ServiceAccount.created_at.desc())

        result = await db.execute(stmt)
        return list(result.scalars().all())

    async def count_service_accounts(
        self,
        db: AsyncSession,
        status: Optional[ServiceAccountStatus] = None
    ) -> int:
        """
        Подсчет количества Service Accounts.

        Args:
            db: Database session
            status: Фильтр по статусу (optional)

        Returns:
            int: Количество Service Accounts
        """
        stmt = select(func.count()).select_from(ServiceAccount)

        if status:
            stmt = stmt.where(ServiceAccount.status == status)

        result = await db.execute(stmt)
        return result.scalar_one()

    async def update_service_account(
        self,
        db: AsyncSession,
        service_account_id: UUID,
        name: Optional[str] = None,
        description: Optional[str] = None,
        role: Optional[ServiceAccountRole] = None,
        rate_limit: Optional[int] = None,
        status: Optional[ServiceAccountStatus] = None
    ) -> Optional[ServiceAccount]:
        """
        Обновление Service Account.

        Args:
            db: Database session
            service_account_id: UUID Service Account
            name: Новое название (optional)
            description: Новое описание (optional)
            role: Новая роль (optional)
            rate_limit: Новый rate limit (optional)
            status: Новый статус (optional)

        Returns:
            Optional[ServiceAccount]: Обновленный Service Account
        """
        service_account = await self.get_by_id(db, service_account_id)
        if not service_account:
            return None

        # Обновление полей
        if name is not None:
            service_account.name = name
        if description is not None:
            service_account.description = description
        if role is not None:
            service_account.role = role
        if rate_limit is not None:
            service_account.rate_limit = rate_limit
        if status is not None:
            service_account.status = status

        await db.commit()
        await db.refresh(service_account)

        logger.info(f"Updated Service Account: {service_account.name} (id={service_account_id})")
        return service_account

    async def rotate_secret(
        self,
        db: AsyncSession,
        service_account_id: UUID,
        expiry_days: int = 90
    ) -> tuple[Optional[ServiceAccount], Optional[str]]:
        """
        Ротация client_secret Service Account с password history tracking.

        Sprint 16 Phase 1: Password history enforcement для предотвращения reuse

        Args:
            db: Database session
            service_account_id: UUID Service Account
            expiry_days: Количество дней до истечения нового secret

        Returns:
            tuple[Optional[ServiceAccount], Optional[str]]: (Service Account, new plain secret)

        Raises:
            ValueError: Если новый секрет совпадает с историей (reuse detected)
        """
        service_account = await self.get_by_id(db, service_account_id)
        if not service_account:
            return None, None

        # Генерация нового секрета
        max_attempts = 3  # Максимум попыток генерации (на случай collision с историей)
        new_secret = None
        new_hash = None

        for attempt in range(max_attempts):
            candidate_secret = self.generate_client_secret()

            # Проверка password history - запрещаем reuse
            current_history = service_account.secret_history or []
            is_reused = self.password_history.check_reuse(candidate_secret, current_history)

            if not is_reused:
                new_secret = candidate_secret
                new_hash = self.hash_secret(new_secret)
                break

            logger.warning(
                f"Password reuse detected for Service Account {service_account.name} "
                f"(attempt {attempt + 1}/{max_attempts})"
            )

        if new_secret is None:
            raise ValueError(
                f"Failed to generate unique password after {max_attempts} attempts. "
                "This is extremely unlikely with proper random generation."
            )

        # Обновление password history
        old_hash = service_account.client_secret_hash
        updated_history = self.password_history.add_to_history(old_hash, current_history)

        # Обновление Service Account
        service_account.client_secret_hash = new_hash
        service_account.secret_history = updated_history
        service_account.secret_changed_at = datetime.now(timezone.utc)
        service_account.secret_expires_at = ServiceAccount.calculate_secret_expiry(days=expiry_days)

        # Если статус был EXPIRED, активируем заново
        if service_account.status == ServiceAccountStatus.EXPIRED:
            service_account.status = ServiceAccountStatus.ACTIVE

        await db.commit()
        await db.refresh(service_account)

        logger.info(
            f"Rotated secret for Service Account: {service_account.name} "
            f"(id={service_account_id}, new_expiry={service_account.secret_expires_at}, "
            f"history_size={len(updated_history)})"
        )

        return service_account, new_secret

    async def delete_service_account(
        self,
        db: AsyncSession,
        service_account_id: UUID,
        soft_delete: bool = True
    ) -> bool:
        """
        Удаление Service Account (soft или hard delete).

        Args:
            db: Database session
            service_account_id: UUID Service Account
            soft_delete: Soft delete (status=DELETED) или hard delete из БД

        Returns:
            bool: True если удаление успешно
        """
        service_account = await self.get_by_id(db, service_account_id)
        if not service_account:
            return False

        # Защита системных аккаунтов
        if service_account.is_system:
            logger.warning(
                f"Cannot delete system Service Account: {service_account.name} "
                f"(id={service_account_id})"
            )
            raise ValueError("Cannot delete system Service Account")

        if soft_delete:
            # Soft delete - помечаем как DELETED
            service_account.status = ServiceAccountStatus.DELETED
            await db.commit()
            logger.info(f"Soft deleted Service Account: {service_account.name} (id={service_account_id})")
        else:
            # Hard delete - удаляем из БД
            await db.delete(service_account)
            await db.commit()
            logger.info(f"Hard deleted Service Account: {service_account.name} (id={service_account_id})")

        return True

    async def authenticate_service_account(
        self,
        db: AsyncSession,
        client_id: str,
        client_secret: str
    ) -> Optional[ServiceAccount]:
        """
        OAuth 2.0 Client Credentials authentication.

        Args:
            db: Database session
            client_id: Client ID
            client_secret: Client Secret (plain)

        Returns:
            Optional[ServiceAccount]: Service Account если аутентификация успешна, None иначе
        """
        # Получение Service Account по client_id
        service_account = await self.get_by_client_id(db, client_id)
        if not service_account:
            logger.warning(f"Service Account not found: {client_id}")
            return None

        # Проверка возможности аутентификации
        if not service_account.can_authenticate():
            logger.warning(
                f"Service Account cannot authenticate: {client_id} "
                f"(status={service_account.status}, expired={service_account.is_expired})"
            )
            return None

        # Проверка client_secret
        if not self.verify_secret(client_secret, service_account.client_secret_hash):
            logger.warning(f"Invalid client_secret for Service Account: {client_id}")
            return None

        # Успешная аутентификация - обновляем last_used_at
        service_account.update_last_used()
        await db.commit()

        logger.info(f"Service Account authenticated successfully: {client_id}")
        return service_account

    async def get_expiring_soon(
        self,
        db: AsyncSession,
        days_threshold: int = 7
    ) -> List[ServiceAccount]:
        """
        Получение Service Accounts с истекающим сроком secret.

        Args:
            db: Database session
            days_threshold: Порог дней до истечения

        Returns:
            List[ServiceAccount]: Service Accounts требующие ротации
        """
        threshold_date = datetime.now(timezone.utc) + timedelta(days=days_threshold)

        stmt = select(ServiceAccount).where(
            ServiceAccount.status == ServiceAccountStatus.ACTIVE,
            ServiceAccount.secret_expires_at <= threshold_date
        ).order_by(ServiceAccount.secret_expires_at)

        result = await db.execute(stmt)
        return list(result.scalars().all())

    async def mark_expired_accounts(self, db: AsyncSession) -> int:
        """
        Пометить просроченные Service Accounts как EXPIRED.

        Должно выполняться периодическим background task.

        Args:
            db: Database session

        Returns:
            int: Количество помеченных аккаунтов
        """
        now = datetime.now(timezone.utc)

        stmt = select(ServiceAccount).where(
            ServiceAccount.status == ServiceAccountStatus.ACTIVE,
            ServiceAccount.secret_expires_at < now
        )

        result = await db.execute(stmt)
        expired_accounts = list(result.scalars().all())

        count = 0
        for account in expired_accounts:
            account.mark_as_expired()
            count += 1

        if count > 0:
            await db.commit()
            logger.info(f"Marked {count} Service Accounts as EXPIRED")

        return count
