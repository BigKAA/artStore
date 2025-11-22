"""
Unit tests для app/db/init_db.py - Initial Admin Auto-Creation

Тестируемые компоненты:
- create_initial_admin(): Автоматическое создание администратора при первом запуске
- Configuration handling: Проверка InitialAdminSettings
- Database logic: Проверка user_count и создание пользователя
- Security: Проверка password hashing и audit logging
"""

import pytest
from unittest.mock import patch
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.db.init_db import create_initial_admin
from app.models.user import User, UserRole, UserStatus
from app.core.config import Settings, InitialAdminSettings


# ==========================================
# Test Configuration Handling
# ==========================================

class TestInitialAdminConfiguration:
    """Тесты для InitialAdminSettings и configuration handling"""

    def test_default_configuration(self):
        """Проверка default конфигурации"""
        config = InitialAdminSettings()

        assert config.enabled is True
        assert config.username == "admin"
        assert config.password == "admin123"
        assert config.email == "admin@artstore.local"
        assert config.firstname == "System"
        assert config.lastname == "Administrator"

    def test_username_trimming(self):
        """Username с пробелами обрезается"""
        config = InitialAdminSettings(username="  admin  ")
        assert config.username == "admin"

    # NOTE: Pydantic Field(default=...) validators are checked during configuration loading
    # from environment variables or config files, not during object construction with defaults.
    # Runtime validation is handled by the database logic in create_initial_admin().


# ==========================================
# Test create_initial_admin Logic
# ==========================================

class TestCreateInitialAdmin:
    """Тесты для create_initial_admin функции"""

    @pytest.mark.asyncio
    async def test_disabled_in_config(self, db_session):
        """Если initial_admin.enabled = False, ничего не создается"""
        settings = Settings()
        settings.initial_admin.enabled = False

        await create_initial_admin(settings, db_session)

        # Проверяем что пользователь НЕ был создан
        result = await db_session.execute(select(func.count()).select_from(User))
        user_count = result.scalar()
        assert user_count == 0

    @pytest.mark.asyncio
    async def test_users_already_exist(self, db_session):
        """Если пользователи уже существуют, новый admin не создается"""
        # Создаем существующего пользователя
        existing_user = User(
            username="existing",
            hashed_password="hash123",
            email="existing@example.com",
            role=UserRole.USER,
            status=UserStatus.ACTIVE
        )
        db_session.add(existing_user)
        await db_session.commit()

        settings = Settings()
        settings.initial_admin.enabled = True

        await create_initial_admin(settings, db_session)

        # Проверяем что был и остался только 1 пользователь
        result = await db_session.execute(select(func.count()).select_from(User))
        user_count = result.scalar()
        assert user_count == 1

        # Проверяем что это НЕ admin
        result = await db_session.execute(
            select(User).where(User.username == settings.initial_admin.username)
        )
        admin_user = result.scalar_one_or_none()
        assert admin_user is None

    @pytest.mark.asyncio
    async def test_create_admin_success(self, db_session):
        """Успешное создание initial admin пользователя"""
        settings = Settings()
        settings.initial_admin.enabled = True
        settings.initial_admin.username = "testadmin"
        settings.initial_admin.password = "TestP@ss123"
        settings.initial_admin.email = "testadmin@example.com"
        settings.initial_admin.firstname = "Test"
        settings.initial_admin.lastname = "Admin"

        await create_initial_admin(settings, db_session)

        # Проверяем что пользователь был создан
        result = await db_session.execute(
            select(User).where(User.username == "testadmin")
        )
        admin_user = result.scalar_one_or_none()

        assert admin_user is not None
        assert admin_user.username == "testadmin"
        assert admin_user.email == "testadmin@example.com"
        assert admin_user.first_name == "Test"
        assert admin_user.last_name == "Admin"
        assert admin_user.role == UserRole.ADMIN
        assert admin_user.status == UserStatus.ACTIVE
        assert admin_user.is_system is True
        assert admin_user.hashed_password is not None
        assert admin_user.hashed_password != "TestP@ss123"  # Должен быть хеш

    @pytest.mark.asyncio
    async def test_password_hashing(self, db_session):
        """Пароль должен быть захеширован, не в plaintext"""
        settings = Settings()
        settings.initial_admin.enabled = True
        settings.initial_admin.password = "PlainPassword123"

        await create_initial_admin(settings, db_session)

        result = await db_session.execute(
            select(User).where(User.username == settings.initial_admin.username)
        )
        admin_user = result.scalar_one()

        # Пароль НЕ должен быть в plaintext
        assert admin_user.hashed_password != "PlainPassword123"

        # Пароль должен быть bcrypt hash
        assert admin_user.hashed_password.startswith("$2b$")

    @pytest.mark.asyncio
    async def test_rollback_on_error(self, db_session):
        """При ошибке создания должен быть rollback"""
        settings = Settings()
        settings.initial_admin.enabled = True

        # Мокируем db.commit() чтобы вызвать ошибку
        with patch.object(db_session, 'commit', side_effect=Exception("DB Error")):
            with pytest.raises(Exception, match="DB Error"):
                await create_initial_admin(settings, db_session)

        # Проверяем что пользователь НЕ был создан (после rollback)
        result = await db_session.execute(select(func.count()).select_from(User))
        user_count = result.scalar()
        assert user_count == 0

    @pytest.mark.asyncio
    async def test_audit_logging(self, db_session, caplog):
        """Создание admin должно быть залогировано для аудита"""
        import logging
        caplog.set_level(logging.INFO)

        settings = Settings()
        settings.initial_admin.enabled = True

        await create_initial_admin(settings, db_session)

        # Проверяем наличие audit лога
        audit_logs = [
            record for record in caplog.records
            if "SECURITY AUDIT" in record.message
        ]
        assert len(audit_logs) > 0

        audit_message = audit_logs[0].message
        assert "Initial administrator" in audit_message
        assert "automatically created" in audit_message

    @pytest.mark.asyncio
    async def test_multiple_calls_idempotent(self, db_session):
        """Повторные вызовы не должны создавать дубликаты"""
        settings = Settings()
        settings.initial_admin.enabled = True

        # Первый вызов создает admin
        await create_initial_admin(settings, db_session)

        # Второй вызов не должен создать дубликат
        await create_initial_admin(settings, db_session)

        # Проверяем что пользователь только ОДИН
        result = await db_session.execute(select(func.count()).select_from(User))
        user_count = result.scalar()
        assert user_count == 1

    @pytest.mark.asyncio
    async def test_with_default_credentials(self, db_session):
        """Создание с default credentials (admin/admin123)"""
        settings = Settings()
        settings.initial_admin.enabled = True
        # Используем default значения

        await create_initial_admin(settings, db_session)

        result = await db_session.execute(
            select(User).where(User.username == "admin")
        )
        admin_user = result.scalar_one_or_none()

        assert admin_user is not None
        assert admin_user.username == "admin"
        assert admin_user.email == "admin@artstore.local"
        assert admin_user.first_name == "System"
        assert admin_user.last_name == "Administrator"


# ==========================================
# Test Security Aspects
# ==========================================

class TestInitialAdminSecurity:
    """Тесты для security аспектов initial admin"""

    @pytest.mark.asyncio
    async def test_password_not_logged(self, db_session, caplog):
        """Пароль НЕ должен попадать в логи"""
        import logging
        caplog.set_level(logging.DEBUG)

        settings = Settings()
        settings.initial_admin.enabled = True
        settings.initial_admin.password = "SuperSecret123"

        await create_initial_admin(settings, db_session)

        # Проверяем что пароль НЕ в логах
        all_logs = " ".join([record.message for record in caplog.records])
        assert "SuperSecret123" not in all_logs

    @pytest.mark.asyncio
    async def test_admin_role_assigned(self, db_session):
        """Созданный пользователь должен иметь роль ADMIN"""
        settings = Settings()
        settings.initial_admin.enabled = True

        await create_initial_admin(settings, db_session)

        result = await db_session.execute(
            select(User).where(User.username == settings.initial_admin.username)
        )
        admin_user = result.scalar_one()

        assert admin_user.role == UserRole.ADMIN

    @pytest.mark.asyncio
    async def test_system_user_flag(self, db_session):
        """Initial admin должен быть is_system=True"""
        settings = Settings()
        settings.initial_admin.enabled = True

        await create_initial_admin(settings, db_session)

        result = await db_session.execute(
            select(User).where(User.username == settings.initial_admin.username)
        )
        admin_user = result.scalar_one()

        assert admin_user.is_system is True

    @pytest.mark.asyncio
    async def test_account_active_by_default(self, db_session):
        """Account должен быть активным по умолчанию"""
        settings = Settings()
        settings.initial_admin.enabled = True

        await create_initial_admin(settings, db_session)

        result = await db_session.execute(
            select(User).where(User.username == settings.initial_admin.username)
        )
        admin_user = result.scalar_one()

        assert admin_user.status == UserStatus.ACTIVE


# ==========================================
# Test Edge Cases
# ==========================================

class TestInitialAdminEdgeCases:
    """Тесты для edge cases"""

    @pytest.mark.asyncio
    async def test_unicode_in_names(self, db_session):
        """Unicode символы в firstname/lastname"""
        settings = Settings()
        settings.initial_admin.enabled = True
        settings.initial_admin.firstname = "Иван"
        settings.initial_admin.lastname = "Петров"

        await create_initial_admin(settings, db_session)

        result = await db_session.execute(
            select(User).where(User.username == settings.initial_admin.username)
        )
        admin_user = result.scalar_one()

        assert admin_user.first_name == "Иван"
        assert admin_user.last_name == "Петров"

    @pytest.mark.asyncio
    async def test_special_chars_in_email(self, db_session):
        """Специальные символы в email"""
        settings = Settings()
        settings.initial_admin.enabled = True
        settings.initial_admin.email = "admin+test@example.co.uk"

        await create_initial_admin(settings, db_session)

        result = await db_session.execute(
            select(User).where(User.username == settings.initial_admin.username)
        )
        admin_user = result.scalar_one()

        assert admin_user.email == "admin+test@example.co.uk"
