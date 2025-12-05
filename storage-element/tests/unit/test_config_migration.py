"""
Тесты миграции параметров конфигурации STORAGE_MAX_SIZE.

Проверяет backward compatibility для:
- STORAGE_MAX_SIZE_GB → STORAGE_MAX_SIZE (bytes)
- STORAGE_S3_SOFT_CAPACITY_LIMIT → STORAGE_MAX_SIZE (bytes)
"""

import os
import warnings
from unittest.mock import patch

import pytest


class TestStorageMaxSizeMigration:
    """Тесты миграции legacy параметров max_size."""

    def setup_method(self):
        """Очистка environment variables перед каждым тестом."""
        # Сохраняем оригинальные значения
        self.original_env = {}
        env_vars = [
            "STORAGE_MAX_SIZE",
            "STORAGE_MAX_SIZE_GB",
            "STORAGE_S3_SOFT_CAPACITY_LIMIT",
            "STORAGE_TYPE",
        ]
        for var in env_vars:
            self.original_env[var] = os.environ.get(var)
            if var in os.environ:
                del os.environ[var]

    def teardown_method(self):
        """Восстановление environment variables после каждого теста."""
        for var, value in self.original_env.items():
            if value is not None:
                os.environ[var] = value
            elif var in os.environ:
                del os.environ[var]

    def test_new_max_size_parameter(self):
        """Новый параметр STORAGE_MAX_SIZE работает корректно."""
        os.environ["STORAGE_MAX_SIZE"] = str(5 * 1024 ** 3)  # 5GB в байтах

        # Импортируем после установки env vars
        from app.core.config import StorageSettings

        settings = StorageSettings()

        assert settings.max_size == 5 * 1024 ** 3
        assert settings.max_size_bytes == 5 * 1024 ** 3  # backward compat property

    def test_default_max_size_value(self):
        """По умолчанию max_size = 1GB."""
        from app.core.config import StorageSettings

        settings = StorageSettings()

        assert settings.max_size == 1 * 1024 ** 3  # 1GB
        assert settings.max_size_gb_display == 1.0
        assert settings.max_size_tb_display == 0.001  # округление

    def test_legacy_max_size_gb_migration(self):
        """Legacy STORAGE_MAX_SIZE_GB мигрируется в max_size с warning."""
        os.environ["STORAGE_MAX_SIZE_GB"] = "5"

        from app.core.config import StorageSettings

        # Проверяем deprecation warning
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            settings = StorageSettings()

            # Должен быть DeprecationWarning
            assert any(
                issubclass(warning.category, DeprecationWarning)
                and "STORAGE_MAX_SIZE_GB" in str(warning.message)
                for warning in w
            )

        # Значение должно быть сконвертировано: 5 GB → bytes
        assert settings.max_size == 5 * 1024 ** 3

    def test_new_max_size_takes_priority_over_legacy(self):
        """Новый STORAGE_MAX_SIZE имеет приоритет над legacy STORAGE_MAX_SIZE_GB."""
        os.environ["STORAGE_MAX_SIZE"] = str(3 * 1024 ** 3)  # 3GB
        os.environ["STORAGE_MAX_SIZE_GB"] = "5"  # 5GB - должен быть проигнорирован

        from app.core.config import StorageSettings

        settings = StorageSettings()

        # Новый параметр имеет приоритет
        assert settings.max_size == 3 * 1024 ** 3

    def test_display_properties(self):
        """Helper properties для отображения размера работают корректно."""
        os.environ["STORAGE_MAX_SIZE"] = str(10 * 1024 ** 4)  # 10TB

        from app.core.config import StorageSettings

        settings = StorageSettings()

        assert settings.max_size == 10 * 1024 ** 4
        assert settings.max_size_gb_display == 10240.0  # 10TB = 10240 GB
        assert settings.max_size_tb_display == 10.0

    def test_max_size_bytes_property_backward_compat(self):
        """Property max_size_bytes возвращает max_size (backward compat)."""
        os.environ["STORAGE_MAX_SIZE"] = str(2 * 1024 ** 3)  # 2GB

        from app.core.config import StorageSettings

        settings = StorageSettings()

        # max_size_bytes теперь просто возвращает max_size
        assert settings.max_size_bytes == settings.max_size
        assert settings.max_size_bytes == 2 * 1024 ** 3


class TestS3SoftCapacityLimitMigration:
    """Тесты миграции legacy S3 soft_capacity_limit параметра."""

    def setup_method(self):
        """Очистка environment variables перед каждым тестом."""
        self.original_env = {}
        env_vars = [
            "STORAGE_MAX_SIZE",
            "STORAGE_MAX_SIZE_GB",
            "STORAGE_S3_SOFT_CAPACITY_LIMIT",
            "STORAGE_TYPE",
        ]
        for var in env_vars:
            self.original_env[var] = os.environ.get(var)
            if var in os.environ:
                del os.environ[var]

    def teardown_method(self):
        """Восстановление environment variables после каждого теста."""
        for var, value in self.original_env.items():
            if value is not None:
                os.environ[var] = value
            elif var in os.environ:
                del os.environ[var]

    def test_legacy_soft_capacity_limit_field_exists(self):
        """Legacy поле legacy_soft_capacity_limit существует в S3StorageSettings."""
        from app.core.config import S3StorageSettings

        settings = S3StorageSettings()

        # Поле существует и по умолчанию None
        assert hasattr(settings, "legacy_soft_capacity_limit")
        assert settings.legacy_soft_capacity_limit is None

    def test_soft_capacity_limit_ignored_for_local_storage(self):
        """STORAGE_S3_SOFT_CAPACITY_LIMIT игнорируется для local storage."""
        os.environ["STORAGE_TYPE"] = "local"
        os.environ["STORAGE_S3_SOFT_CAPACITY_LIMIT"] = str(10 * 1024 ** 4)  # 10TB

        from app.core.config import StorageSettings

        settings = StorageSettings()

        # Для local storage должен использоваться default, не soft_capacity_limit
        assert settings.max_size == 1 * 1024 ** 3  # Default 1GB

    def test_max_size_gb_priority_over_soft_capacity_limit(self):
        """STORAGE_MAX_SIZE_GB имеет приоритет над STORAGE_S3_SOFT_CAPACITY_LIMIT."""
        os.environ["STORAGE_TYPE"] = "s3"
        os.environ["STORAGE_MAX_SIZE_GB"] = "5"  # 5GB
        os.environ["STORAGE_S3_SOFT_CAPACITY_LIMIT"] = str(10 * 1024 ** 4)  # 10TB

        from app.core.config import StorageSettings

        settings = StorageSettings()

        # max_size_gb имеет приоритет (проверяется первым в validator)
        assert settings.max_size == 5 * 1024 ** 3  # 5GB, не 10TB
