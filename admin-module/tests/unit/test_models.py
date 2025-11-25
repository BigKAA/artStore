"""
Unit тесты для моделей Admin Module.
"""

import pytest
from datetime import datetime, timedelta

from app.models import (
    User, UserRole, UserStatus,
    StorageElement, StorageMode, StorageType, StorageStatus
)


class TestUserModel:
    """Тесты для модели User."""

    def test_user_creation(self):
        """Тест создания пользователя."""
        user = User(
            username="testuser",
            email="test@example.com",
            first_name="Test",
            last_name="User",
            role=UserRole.USER,
            status=UserStatus.ACTIVE
        )

        assert user.username == "testuser"
        assert user.email == "test@example.com"
        assert user.full_name == "Test User"
        assert user.role == UserRole.USER
        assert user.status == UserStatus.ACTIVE
        assert user.is_active is True

    def test_user_full_name(self):
        """Тест получения полного имени."""
        # Оба имени
        user1 = User(
            username="user1",
            email="user1@example.com",
            first_name="John",
            last_name="Doe"
        )
        assert user1.full_name == "John Doe"

        # Только first_name
        user2 = User(
            username="user2",
            email="user2@example.com",
            first_name="John"
        )
        assert user2.full_name == "John"

        # Только last_name
        user3 = User(
            username="user3",
            email="user3@example.com",
            last_name="Doe"
        )
        assert user3.full_name == "Doe"

        # Без имен - username
        user4 = User(
            username="user4",
            email="user4@example.com"
        )
        assert user4.full_name == "user4"

    def test_user_is_local_user(self):
        """Тест определения локального пользователя."""
        local_user = User(
            username="localuser",
            email="local@example.com",
            hashed_password="hashed_password_here"
        )
        assert local_user.is_local_user is True

    def test_user_can_login_active(self):
        """Тест возможности входа для активного пользователя."""
        user = User(
            username="activeuser",
            email="active@example.com",
            hashed_password="hashed",
            status=UserStatus.ACTIVE
        )
        assert user.can_login() is True

    def test_user_can_login_inactive(self):
        """Тест запрета входа для неактивного пользователя."""
        user = User(
            username="inactive",
            email="inactive@example.com",
            hashed_password="hashed",
            status=UserStatus.INACTIVE
        )
        assert user.can_login() is False

    def test_user_can_login_locked(self):
        """Тест запрета входа для заблокированного пользователя."""
        user = User(
            username="locked",
            email="locked@example.com",
            hashed_password="hashed",
            status=UserStatus.LOCKED,
            lockout_until=datetime.utcnow() + timedelta(minutes=30)
        )
        assert user.can_login() is False

    def test_user_can_login_lockout_expired(self):
        """Тест возможности входа после истечения блокировки."""
        user = User(
            username="unlocked",
            email="unlocked@example.com",
            hashed_password="hashed",
            status=UserStatus.ACTIVE,
            lockout_until=datetime.utcnow() - timedelta(minutes=1)  # Истекла
        )
        assert user.can_login() is True

    def test_user_reset_failed_attempts(self):
        """Тест сброса счетчика неудачных попыток."""
        user = User(
            username="user",
            email="user@example.com",
            failed_login_attempts=5,
            lockout_until=datetime.utcnow() + timedelta(minutes=30)
        )

        user.reset_failed_attempts()

        assert user.failed_login_attempts == 0
        assert user.lockout_until is None

    def test_user_increment_failed_attempts(self):
        """Тест увеличения счетчика неудачных попыток."""
        user = User(
            username="user",
            email="user@example.com",
            hashed_password="hashed",
            status=UserStatus.ACTIVE,
            failed_login_attempts=0
        )

        # Первая попытка
        user.increment_failed_attempts(lockout_threshold=3)
        assert user.failed_login_attempts == 1
        assert user.lockout_until is None
        assert user.status == UserStatus.ACTIVE

        # Вторая попытка
        user.increment_failed_attempts(lockout_threshold=3)
        assert user.failed_login_attempts == 2
        assert user.lockout_until is None

        # Третья попытка - блокировка
        user.increment_failed_attempts(lockout_threshold=3)
        assert user.failed_login_attempts == 3
        assert user.lockout_until is not None
        assert user.status == UserStatus.LOCKED


class TestStorageElementModel:
    """Тесты для модели StorageElement."""

    def test_storage_element_creation(self):
        """Тест создания storage element."""
        storage = StorageElement(
            name="storage01",
            description="Test storage",
            mode=StorageMode.EDIT,
            storage_type=StorageType.LOCAL,
            base_path="/data/storage01",
            api_url="http://localhost:8010",
            status=StorageStatus.ONLINE
        )

        assert storage.name == "storage01"
        assert storage.mode == StorageMode.EDIT
        assert storage.storage_type == StorageType.LOCAL
        assert storage.is_available is True

    def test_storage_is_writable(self):
        """Тест проверки возможности записи."""
        # EDIT - writable
        edit_storage = StorageElement(
            name="edit",
            mode=StorageMode.EDIT,
            storage_type=StorageType.LOCAL,
            base_path="/data",
            api_url="http://localhost:8010",
            status=StorageStatus.ONLINE
        )
        assert edit_storage.is_writable is True

        # RW - writable
        rw_storage = StorageElement(
            name="rw",
            mode=StorageMode.RW,
            storage_type=StorageType.LOCAL,
            base_path="/data",
            api_url="http://localhost:8010",
            status=StorageStatus.ONLINE
        )
        assert rw_storage.is_writable is True

        # RO - not writable
        ro_storage = StorageElement(
            name="ro",
            mode=StorageMode.RO,
            storage_type=StorageType.LOCAL,
            base_path="/data",
            api_url="http://localhost:8010",
            status=StorageStatus.ONLINE
        )
        assert ro_storage.is_writable is False

    def test_storage_is_deletable(self):
        """Тест проверки возможности удаления файлов."""
        # Только EDIT режим позволяет удаление
        edit_storage = StorageElement(
            name="edit",
            mode=StorageMode.EDIT,
            storage_type=StorageType.LOCAL,
            base_path="/data",
            api_url="http://localhost:8010",
            status=StorageStatus.ONLINE
        )
        assert edit_storage.is_deletable is True

        rw_storage = StorageElement(
            name="rw",
            mode=StorageMode.RW,
            storage_type=StorageType.LOCAL,
            base_path="/data",
            api_url="http://localhost:8010",
            status=StorageStatus.ONLINE
        )
        assert rw_storage.is_deletable is False

    def test_storage_usage_percentage(self):
        """Тест расчета процента использования."""
        storage = StorageElement(
            name="storage",
            mode=StorageMode.EDIT,
            storage_type=StorageType.LOCAL,
            base_path="/data",
            api_url="http://localhost:8010",
            capacity_bytes=1000000,
            used_bytes=250000
        )

        assert storage.usage_percentage == 25.0

    def test_storage_available_bytes(self):
        """Тест расчета доступного места."""
        storage = StorageElement(
            name="storage",
            mode=StorageMode.EDIT,
            storage_type=StorageType.LOCAL,
            base_path="/data",
            api_url="http://localhost:8010",
            capacity_bytes=1000000,
            used_bytes=250000
        )

        assert storage.available_bytes == 750000

    def test_storage_can_transition_to(self):
        """Тест возможности перехода между режимами."""
        # EDIT - не может быть изменен
        edit_storage = StorageElement(
            name="edit",
            mode=StorageMode.EDIT,
            storage_type=StorageType.LOCAL,
            base_path="/data",
            api_url="http://localhost:8010"
        )
        assert edit_storage.can_transition_to(StorageMode.RW) is False
        assert edit_storage.can_transition_to(StorageMode.RO) is False

        # RW -> RO
        rw_storage = StorageElement(
            name="rw",
            mode=StorageMode.RW,
            storage_type=StorageType.LOCAL,
            base_path="/data",
            api_url="http://localhost:8010"
        )
        assert rw_storage.can_transition_to(StorageMode.RO) is True
        assert rw_storage.can_transition_to(StorageMode.AR) is False

        # RO -> AR
        ro_storage = StorageElement(
            name="ro",
            mode=StorageMode.RO,
            storage_type=StorageType.LOCAL,
            base_path="/data",
            api_url="http://localhost:8010"
        )
        assert ro_storage.can_transition_to(StorageMode.AR) is True
        assert ro_storage.can_transition_to(StorageMode.RW) is False

        # AR - не может быть изменен через API
        ar_storage = StorageElement(
            name="ar",
            mode=StorageMode.AR,
            storage_type=StorageType.LOCAL,
            base_path="/data",
            api_url="http://localhost:8010"
        )
        assert ar_storage.can_transition_to(StorageMode.RO) is False
        assert ar_storage.can_transition_to(StorageMode.RW) is False

    def test_storage_has_sufficient_space(self):
        """Тест проверки достаточности свободного места."""
        storage = StorageElement(
            name="storage",
            mode=StorageMode.EDIT,
            storage_type=StorageType.LOCAL,
            base_path="/data",
            api_url="http://localhost:8010",
            capacity_bytes=1000000,
            used_bytes=250000
        )

        # Достаточно места
        assert storage.has_sufficient_space(500000) is True

        # Недостаточно места
        assert storage.has_sufficient_space(1000000) is False

    def test_storage_update_usage(self):
        """Тест обновления статистики использования."""
        storage = StorageElement(
            name="storage",
            mode=StorageMode.EDIT,
            storage_type=StorageType.LOCAL,
            base_path="/data",
            api_url="http://localhost:8010",
            used_bytes=1000,
            file_count=10
        )

        # Добавляем данные
        storage.update_usage(bytes_delta=500, files_delta=5)
        assert storage.used_bytes == 1500
        assert storage.file_count == 15

        # Удаляем данные
        storage.update_usage(bytes_delta=-500, files_delta=-5)
        assert storage.used_bytes == 1000
        assert storage.file_count == 10

        # Проверка что значения не становятся отрицательными
        storage.update_usage(bytes_delta=-2000, files_delta=-20)
        assert storage.used_bytes == 0
        assert storage.file_count == 0
