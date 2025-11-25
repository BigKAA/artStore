"""
Unit tests для ServiceAccount model и ServiceAccountService.

Тесты покрывают:
- Создание и валидацию Service Account
- Генерацию client_id и client_secret
- Хеширование и верификацию секретов
- OAuth 2.0 аутентификацию
- Ротацию секретов
- Управление статусами
- Проверку истечения срока действия
"""

import pytest
from datetime import datetime, timedelta, timezone
from uuid import UUID

from app.models.service_account import (
    ServiceAccount,
    ServiceAccountRole,
    ServiceAccountStatus
)
from app.services.service_account_service import ServiceAccountService


# ========================================================================
# MODEL TESTS
# ========================================================================

class TestServiceAccountModel:
    """Тесты для ServiceAccount model."""

    def test_service_account_creation(self):
        """Тест создания Service Account с валидными данными."""
        service_account = ServiceAccount(
            name="Test Service Account",
            description="Test description",
            client_id="sa_test_client_123",
            client_secret_hash="hashed_secret",
            role=ServiceAccountRole.USER,
            status=ServiceAccountStatus.ACTIVE,
            rate_limit=100,
            is_system=False,
            secret_expires_at=datetime.now(timezone.utc) + timedelta(days=90)
        )

        assert service_account.name == "Test Service Account"
        assert service_account.client_id == "sa_test_client_123"
        assert service_account.role == ServiceAccountRole.USER
        assert service_account.status == ServiceAccountStatus.ACTIVE
        assert service_account.rate_limit == 100
        assert service_account.is_system is False

    def test_service_account_can_authenticate_active(self):
        """Тест can_authenticate для активного Service Account."""
        service_account = ServiceAccount(
            name="Active SA",
            client_id="sa_active_123",
            client_secret_hash="hash",
            role=ServiceAccountRole.USER,
            status=ServiceAccountStatus.ACTIVE,
            secret_expires_at=datetime.now(timezone.utc) + timedelta(days=30)
        )

        assert service_account.can_authenticate() is True

    def test_service_account_cannot_authenticate_suspended(self):
        """Тест can_authenticate для приостановленного Service Account."""
        service_account = ServiceAccount(
            name="Suspended SA",
            client_id="sa_suspended_123",
            client_secret_hash="hash",
            role=ServiceAccountRole.USER,
            status=ServiceAccountStatus.SUSPENDED,
            secret_expires_at=datetime.now(timezone.utc) + timedelta(days=30)
        )

        assert service_account.can_authenticate() is False

    def test_service_account_cannot_authenticate_expired(self):
        """Тест can_authenticate для Service Account с истекшим секретом."""
        service_account = ServiceAccount(
            name="Expired SA",
            client_id="sa_expired_123",
            client_secret_hash="hash",
            role=ServiceAccountRole.USER,
            status=ServiceAccountStatus.ACTIVE,
            secret_expires_at=datetime.now(timezone.utc) - timedelta(days=1)  # Истек вчера
        )

        assert service_account.can_authenticate() is False
        assert service_account.is_expired is True

    def test_service_account_days_until_expiry(self):
        """Тест вычисления дней до истечения секрета."""
        service_account = ServiceAccount(
            name="Test SA",
            client_id="sa_test_123",
            client_secret_hash="hash",
            role=ServiceAccountRole.USER,
            secret_expires_at=datetime.now(timezone.utc) + timedelta(days=15)
        )

        days = service_account.days_until_expiry
        assert 14 <= days <= 16  # Допускаем небольшую погрешность

    def test_service_account_requires_rotation_warning(self):
        """Тест флага предупреждения о ротации (≤7 дней до истечения)."""
        # Секрет истекает через 5 дней - требуется предупреждение
        service_account = ServiceAccount(
            name="Warning SA",
            client_id="sa_warning_123",
            client_secret_hash="hash",
            role=ServiceAccountRole.USER,
            secret_expires_at=datetime.now(timezone.utc) + timedelta(days=5)
        )
        assert service_account.requires_rotation_warning is True

        # Секрет истекает через 30 дней - предупреждение не требуется
        service_account.secret_expires_at = datetime.now(timezone.utc) + timedelta(days=30)
        assert service_account.requires_rotation_warning is False

    def test_service_account_update_last_used(self):
        """Тест обновления времени последнего использования."""
        service_account = ServiceAccount(
            name="Test SA",
            client_id="sa_test_123",
            client_secret_hash="hash",
            role=ServiceAccountRole.USER,
            last_used_at=None
        )

        assert service_account.last_used_at is None

        service_account.update_last_used()

        assert service_account.last_used_at is not None
        assert isinstance(service_account.last_used_at, datetime)

    def test_service_account_generate_client_id(self):
        """Тест статического метода генерации client_id."""
        client_id = ServiceAccount.generate_client_id(
            name="MyApp Production",
            environment="prod"
        )

        # Формат: sa_{env}_{name}_{random}
        assert client_id.startswith("sa_prod_myapp_")
        assert len(client_id) > 20

    def test_service_account_calculate_secret_expiry(self):
        """Тест статического метода вычисления срока истечения."""
        expiry = ServiceAccount.calculate_secret_expiry(days=90)

        assert expiry > datetime.now(timezone.utc)
        delta = expiry - datetime.now(timezone.utc)
        assert 89 <= delta.days <= 91


# ========================================================================
# SERVICE TESTS
# ========================================================================

class TestServiceAccountService:
    """Тесты для ServiceAccountService."""

    def test_generate_client_secret(self):
        """Тест генерации client_secret."""
        service = ServiceAccountService()

        secret = service.generate_client_secret(length=48)

        assert len(secret) == 48
        # Проверяем что секрет содержит разные типы символов
        assert any(c.isupper() for c in secret)
        assert any(c.islower() for c in secret)
        assert any(c.isdigit() for c in secret)

    def test_generate_client_secret_custom_length(self):
        """Тест генерации секрета кастомной длины."""
        service = ServiceAccountService()

        secret = service.generate_client_secret(length=64)

        assert len(secret) == 64

    def test_hash_and_verify_secret(self):
        """Тест хеширования и верификации секрета."""
        service = ServiceAccountService()

        secret = "my_super_secret_123!@#"
        hashed = service.hash_secret(secret)

        # Проверяем что hash отличается от исходного секрета
        assert hashed != secret
        assert len(hashed) > 0

        # Проверяем верификацию правильного секрета
        assert service.verify_secret(secret, hashed) is True

        # Проверяем что неправильный секрет не проходит верификацию
        assert service.verify_secret("wrong_secret", hashed) is False

    @pytest.mark.asyncio
    async def test_create_service_account(self, db_session):
        """Тест создания Service Account в БД."""
        service = ServiceAccountService()

        service_account, plain_secret = await service.create_service_account(
            db=db_session,
            name="Test Production Client",
            description="Test description",
            role=ServiceAccountRole.USER,
            rate_limit=100,
            environment="prod",
            is_system=False
        )

        # Проверяем что запись создана
        assert service_account.id is not None
        assert isinstance(service_account.id, UUID)
        assert service_account.name == "Test Production Client"
        assert service_account.client_id.startswith("sa_prod_test_")
        assert service_account.role == ServiceAccountRole.USER
        assert service_account.status == ServiceAccountStatus.ACTIVE
        assert service_account.rate_limit == 100
        assert service_account.secret_expires_at is not None

        # Проверяем что client_secret_hash создан
        assert service_account.client_secret_hash is not None
        assert len(service_account.client_secret_hash) > 0

        # Проверяем что возвращен plaintext secret
        assert plain_secret is not None
        assert len(plain_secret) == 16  # Default length (min_length + 4 = 12 + 4)

    @pytest.mark.asyncio
    async def test_get_by_client_id(self, db_session):
        """Тест поиска Service Account по client_id."""
        service = ServiceAccountService()

        # Создаем Service Account
        created, _ = await service.create_service_account(
            db=db_session,
            name="Find Me",
            role=ServiceAccountRole.USER,
            environment="staging"
        )

        # Ищем по client_id
        found = await service.get_by_client_id(db_session, created.client_id)

        assert found is not None
        assert found.id == created.id
        assert found.client_id == created.client_id

    @pytest.mark.asyncio
    async def test_get_by_client_id_not_found(self, db_session):
        """Тест поиска несуществующего Service Account."""
        service = ServiceAccountService()

        found = await service.get_by_client_id(
            db_session,
            "sa_nonexistent_123"
        )

        assert found is None

    @pytest.mark.asyncio
    async def test_authenticate_service_account_success(self, db_session):
        """Тест успешной OAuth аутентификации Service Account."""
        service = ServiceAccountService()

        # Создаем Service Account и сохраняем plaintext secret
        created, plain_secret = await service.create_service_account(
            db=db_session,
            name="Auth Test",
            role=ServiceAccountRole.USER
        )

        # Аутентифицируемся с правильными credentials
        authenticated = await service.authenticate_service_account(
            db=db_session,
            client_id=created.client_id,
            client_secret=plain_secret
        )

        assert authenticated is not None
        assert authenticated.id == created.id
        assert authenticated.last_used_at is not None  # Обновлено время использования

    @pytest.mark.asyncio
    async def test_authenticate_service_account_wrong_secret(self, db_session):
        """Тест аутентификации с неправильным секретом."""
        service = ServiceAccountService()

        created, _ = await service.create_service_account(
            db=db_session,
            name="Auth Fail Test",
            role=ServiceAccountRole.USER
        )

        # Пытаемся аутентифицироваться с неправильным секретом
        authenticated = await service.authenticate_service_account(
            db=db_session,
            client_id=created.client_id,
            client_secret="wrong_secret_123"
        )

        assert authenticated is None

    @pytest.mark.asyncio
    async def test_authenticate_service_account_suspended(self, db_session):
        """Тест аутентификации приостановленного Service Account."""
        service = ServiceAccountService()

        created, plain_secret = await service.create_service_account(
            db=db_session,
            name="Suspended Test",
            role=ServiceAccountRole.USER
        )

        # Приостанавливаем Service Account
        await service.update_service_account(
            db=db_session,
            service_account_id=created.id,
            status=ServiceAccountStatus.SUSPENDED
        )

        # Пытаемся аутентифицироваться
        authenticated = await service.authenticate_service_account(
            db=db_session,
            client_id=created.client_id,
            client_secret=plain_secret
        )

        assert authenticated is None

    @pytest.mark.asyncio
    async def test_rotate_secret(self, db_session):
        """Тест ротации client_secret."""
        service = ServiceAccountService()

        created, old_secret = await service.create_service_account(
            db=db_session,
            name="Rotation Test",
            role=ServiceAccountRole.USER
        )

        old_hash = created.client_secret_hash

        # Выполняем ротацию
        rotated, new_secret = await service.rotate_secret(
            db=db_session,
            service_account_id=created.id
        )

        # Проверяем что секрет изменился
        assert rotated.client_secret_hash != old_hash
        assert new_secret != old_secret

        # Проверяем что старый секрет больше не работает
        auth_old = await service.authenticate_service_account(
            db=db_session,
            client_id=created.client_id,
            client_secret=old_secret
        )
        assert auth_old is None

        # Проверяем что новый секрет работает
        auth_new = await service.authenticate_service_account(
            db=db_session,
            client_id=created.client_id,
            client_secret=new_secret
        )
        assert auth_new is not None

    @pytest.mark.asyncio
    async def test_soft_delete(self, db_session):
        """Тест soft delete Service Account."""
        service = ServiceAccountService()

        created, _ = await service.create_service_account(
            db=db_session,
            name="Delete Test",
            role=ServiceAccountRole.USER
        )

        # Мягко удаляем
        deleted = await service.delete_service_account(db_session, created.id)

        assert deleted is True

        # Проверяем что запись помечена как удаленная (через status)
        found = await service.get_by_id(db_session, created.id)
        assert found.status == ServiceAccountStatus.DELETED

    @pytest.mark.asyncio
    async def test_list_active_service_accounts(self, db_session):
        """Тест получения списка активных Service Accounts."""
        service = ServiceAccountService()

        # Создаем несколько Service Accounts
        await service.create_service_account(
            db_session, name="SA 1", role=ServiceAccountRole.USER
        )
        await service.create_service_account(
            db_session, name="SA 2", role=ServiceAccountRole.USER
        )
        suspended, _ = await service.create_service_account(
            db_session, name="SA 3", role=ServiceAccountRole.USER
        )

        # Приостанавливаем один
        await service.update_service_account(
            db_session,
            suspended.id,
            status=ServiceAccountStatus.SUSPENDED
        )

        # Получаем список активных
        active_list = await service.list_service_accounts(
            db=db_session,
            status=ServiceAccountStatus.ACTIVE
        )

        assert len(active_list) >= 2
        assert all(sa.status == ServiceAccountStatus.ACTIVE for sa in active_list)

    @pytest.mark.asyncio
    async def test_get_expiring_soon_service_accounts(self, db_session):
        """Тест получения Service Accounts с истекающими скоро секретами."""
        service = ServiceAccountService()

        # Создаем SA с секретом, истекающим скоро (вручную устанавливаем дату)
        sa_expiring, _ = await service.create_service_account(
            db_session,
            name="Expiring Soon",
            role=ServiceAccountRole.USER
        )
        # Обновляем дату истечения на 5 дней
        sa_expiring.secret_expires_at = datetime.now(timezone.utc) + timedelta(days=5)
        db_session.add(sa_expiring)
        await db_session.commit()

        # Создаем SA с секретом, истекающим через 90 дней
        sa_normal, _ = await service.create_service_account(
            db_session,
            name="Normal SA",
            role=ServiceAccountRole.USER
        )

        # Получаем список с истекающими скоро (≤7 дней)
        expiring_list = await service.get_expiring_soon(
            db=db_session,
            days_threshold=7
        )

        # Проверяем что нашли SA с истекающим секретом
        expiring_ids = [sa.id for sa in expiring_list]
        assert sa_expiring.id in expiring_ids
        assert sa_normal.id not in expiring_ids
