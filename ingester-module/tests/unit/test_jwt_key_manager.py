"""
Unit тесты для JWTKeyManager hot-reload функционала (Ingester Module).

Тестирует:
- Инициализацию JWTKeyManager с валидными ключами
- Автоматический hot-reload при изменении файла ключа
- Thread-safe операции при конкурентном доступе к ключам
"""

import pytest
import asyncio
from pathlib import Path
import tempfile
import time

from app.core.jwt_key_manager import JWTKeyManager


@pytest.mark.asyncio
async def test_jwt_key_manager_initialization():
    """Тест инициализации JWTKeyManager с валидными ключами."""
    with tempfile.TemporaryDirectory() as tmpdir:
        key_path = Path(tmpdir) / "public_key.pem"

        # Создать валидный PEM ключ
        test_key = "-----BEGIN PUBLIC KEY-----\nTEST_KEY_CONTENT\n-----END PUBLIC KEY-----"
        key_path.write_text(test_key)

        # Инициализировать manager (hot-reload отключен для теста)
        manager = JWTKeyManager(
            public_key_path=str(key_path),
            enable_hot_reload=False
        )

        # Проверить что ключ загружен
        assert manager.get_public_key_sync() == test_key
        print("✅ JWTKeyManager initialization test passed")


@pytest.mark.asyncio
async def test_hot_reload_on_file_change():
    """Тест автоматического hot-reload при изменении файла ключа."""
    with tempfile.TemporaryDirectory() as tmpdir:
        key_path = Path(tmpdir) / "public_key.pem"

        # Создать начальный ключ
        initial_key = "-----BEGIN PUBLIC KEY-----\nINITIAL_KEY\n-----END PUBLIC KEY-----"
        key_path.write_text(initial_key)

        # Инициализировать manager с hot-reload
        manager = JWTKeyManager(
            public_key_path=str(key_path),
            enable_hot_reload=True
        )

        # Проверить начальное значение
        assert manager.get_public_key_sync() == initial_key

        # Запустить file watcher (требует async контекст)
        manager.start_watching()

        # Дать время watcher'у запуститься
        await asyncio.sleep(0.5)

        # Изменить ключ
        updated_key = "-----BEGIN PUBLIC KEY-----\nUPDATED_KEY\n-----END PUBLIC KEY-----"
        key_path.write_text(updated_key)

        # Подождать hot-reload (watchfiles обычно реагирует за <1s)
        await asyncio.sleep(2)

        # Проверить что ключ обновился
        assert manager.get_public_key_sync() == updated_key
        print("✅ Hot-reload test passed")


@pytest.mark.asyncio
async def test_concurrent_key_access():
    """Тест thread-safety при конкурентном доступе к ключам."""
    with tempfile.TemporaryDirectory() as tmpdir:
        key_path = Path(tmpdir) / "public_key.pem"

        # Создать ключ
        test_key = "-----BEGIN PUBLIC KEY-----\nTEST_KEY\n-----END PUBLIC KEY-----"
        key_path.write_text(test_key)

        # Инициализировать manager
        manager = JWTKeyManager(
            public_key_path=str(key_path),
            enable_hot_reload=False
        )

        # Параллельное чтение ключа (10 coroutines)
        async def read_key():
            return manager.get_public_key_sync()

        results = await asyncio.gather(*[read_key() for _ in range(10)])

        # Проверить что все результаты одинаковые
        assert all(r == test_key for r in results)
        print("✅ Concurrent access test passed")


@pytest.mark.asyncio
async def test_invalid_pem_format_graceful_handling():
    """Тест graceful error handling при невалидном PEM формате."""
    with tempfile.TemporaryDirectory() as tmpdir:
        key_path = Path(tmpdir) / "public_key.pem"

        # Создать валидный ключ
        valid_key = "-----BEGIN PUBLIC KEY-----\nVALID_KEY\n-----END PUBLIC KEY-----"
        key_path.write_text(valid_key)

        # Инициализировать manager с hot-reload
        manager = JWTKeyManager(
            public_key_path=str(key_path),
            enable_hot_reload=True
        )

        # Проверить начальное значение
        assert manager.get_public_key_sync() == valid_key

        # Запустить file watcher
        manager.start_watching()
        await asyncio.sleep(0.5)

        # Записать НЕВАЛИДНЫЙ ключ (без -----BEGIN)
        invalid_key = "INVALID_KEY_FORMAT"
        key_path.write_text(invalid_key)

        # Подождать попытку hot-reload
        await asyncio.sleep(2)

        # Проверить что ключ НЕ обновился (graceful fallback на старый)
        assert manager.get_public_key_sync() == valid_key
        print("✅ Invalid PEM format graceful handling test passed")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
