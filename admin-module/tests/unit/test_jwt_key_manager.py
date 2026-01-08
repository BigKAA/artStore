"""
Unit тесты для JWTKeyManager (dual-key version для Admin Module).

Sprint: JWT Hot-Reload Implementation (2026-01-08)

Тесты:
- Инициализация с валидными ключами (dual-key)
- Автоматический hot-reload при изменении файлов
- Thread-safety при конкурентном доступе к ключам
- Graceful error handling при невалидных ключах
"""

import pytest
import asyncio
from pathlib import Path
import tempfile
import sys
import os

# Устанавливаем минимальные environment variables для избежания config errors
os.environ['APP_DEBUG'] = 'off'
os.environ['JWT_PRIVATE_KEY_PATH'] = '/tmp/test_private.pem'
os.environ['JWT_PUBLIC_KEY_PATH'] = '/tmp/test_public.pem'

# Прямой импорт JWTKeyManager без dependencies
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from app.core.jwt_key_manager import JWTKeyManager


# Sample PEM keys для тестирования
SAMPLE_PRIVATE_KEY = """-----BEGIN RSA PRIVATE KEY-----
MIIEpAIBAAKCAQEA3Z3n...TEST_PRIVATE_KEY...Fake
-----END RSA PRIVATE KEY-----"""

SAMPLE_PUBLIC_KEY = """-----BEGIN PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0...TEST_PUBLIC_KEY...Fake
-----END PUBLIC KEY-----"""

UPDATED_PRIVATE_KEY = """-----BEGIN RSA PRIVATE KEY-----
UPDATED_PRIVATE_KEY_CONTENT...TEST
-----END RSA PRIVATE KEY-----"""

UPDATED_PUBLIC_KEY = """-----BEGIN PUBLIC KEY-----
UPDATED_PUBLIC_KEY_CONTENT...TEST
-----END PUBLIC KEY-----"""


@pytest.mark.asyncio
async def test_jwt_key_manager_initialization():
    """
    Тест инициализации JWTKeyManager с валидными ключами (dual-key).

    Проверяет:
    - Успешная загрузка private и public ключей
    - Ключи доступны через sync методы
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        private_key_path = Path(tmpdir) / "private_key.pem"
        public_key_path = Path(tmpdir) / "public_key.pem"

        # Создать тестовые ключи
        private_key_path.write_text(SAMPLE_PRIVATE_KEY)
        public_key_path.write_text(SAMPLE_PUBLIC_KEY)

        # Инициализировать manager
        manager = JWTKeyManager(
            private_key_path=str(private_key_path),
            public_key_path=str(public_key_path),
            enable_hot_reload=False  # Отключаем hot-reload для простого теста
        )

        # Проверить что ключи загружены
        assert manager.get_private_key_sync() == SAMPLE_PRIVATE_KEY
        assert manager.get_public_key_sync() == SAMPLE_PUBLIC_KEY


@pytest.mark.asyncio
async def test_hot_reload_on_file_change():
    """
    Тест автоматического hot-reload при изменении файлов ключей (dual-key).

    Проверяет:
    - Watcher обнаруживает изменения файлов
    - Ключи автоматически перезагружаются
    - Новые значения доступны после hot-reload
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        private_key_path = Path(tmpdir) / "private_key.pem"
        public_key_path = Path(tmpdir) / "public_key.pem"

        # Создать начальные ключи
        private_key_path.write_text(SAMPLE_PRIVATE_KEY)
        public_key_path.write_text(SAMPLE_PUBLIC_KEY)

        # Инициализировать manager с hot-reload
        manager = JWTKeyManager(
            private_key_path=str(private_key_path),
            public_key_path=str(public_key_path),
            enable_hot_reload=True
        )

        # Проверить начальные значения
        assert manager.get_private_key_sync() == SAMPLE_PRIVATE_KEY
        assert manager.get_public_key_sync() == SAMPLE_PUBLIC_KEY

        # Запустить watcher (требует async context)
        manager.start_watching()

        # Подождать запуска watcher
        await asyncio.sleep(0.5)

        # Изменить ключи
        private_key_path.write_text(UPDATED_PRIVATE_KEY)
        public_key_path.write_text(UPDATED_PUBLIC_KEY)

        # Подождать hot-reload (watchfiles обычно реагирует за <2s)
        await asyncio.sleep(3)

        # Проверить что ключи обновились
        assert manager.get_private_key_sync() == UPDATED_PRIVATE_KEY
        assert manager.get_public_key_sync() == UPDATED_PUBLIC_KEY

        # Остановить watcher
        await manager.stop_watching()


@pytest.mark.asyncio
async def test_concurrent_key_access():
    """
    Тест thread-safety при конкурентном доступе к ключам (dual-key).

    Проверяет:
    - Параллельные чтения ключей безопасны
    - Нет race conditions при одновременном доступе
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        private_key_path = Path(tmpdir) / "private_key.pem"
        public_key_path = Path(tmpdir) / "public_key.pem"

        # Создать тестовые ключи
        private_key_path.write_text(SAMPLE_PRIVATE_KEY)
        public_key_path.write_text(SAMPLE_PUBLIC_KEY)

        # Инициализировать manager
        manager = JWTKeyManager(
            private_key_path=str(private_key_path),
            public_key_path=str(public_key_path),
            enable_hot_reload=False
        )

        # Параллельные чтения ключей
        async def read_keys_multiple_times():
            for _ in range(10):
                private_key = manager.get_private_key_sync()
                public_key = manager.get_public_key_sync()
                assert private_key == SAMPLE_PRIVATE_KEY
                assert public_key == SAMPLE_PUBLIC_KEY
                await asyncio.sleep(0.01)

        # Запустить 5 параллельных задач
        tasks = [read_keys_multiple_times() for _ in range(5)]
        await asyncio.gather(*tasks)

        # Если добрались сюда без exceptions - thread-safety работает


@pytest.mark.asyncio
async def test_invalid_pem_format_graceful_handling():
    """
    Тест graceful error handling при невалидных ключах (dual-key).

    Проверяет:
    - Невалидные ключи не ломают приложение
    - Старые ключи остаются доступными при ошибке hot-reload
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        private_key_path = Path(tmpdir) / "private_key.pem"
        public_key_path = Path(tmpdir) / "public_key.pem"

        # Создать начальные валидные ключи
        private_key_path.write_text(SAMPLE_PRIVATE_KEY)
        public_key_path.write_text(SAMPLE_PUBLIC_KEY)

        # Инициализировать manager с hot-reload
        manager = JWTKeyManager(
            private_key_path=str(private_key_path),
            public_key_path=str(public_key_path),
            enable_hot_reload=True
        )

        # Проверить начальные значения
        initial_private = manager.get_private_key_sync()
        initial_public = manager.get_public_key_sync()
        assert initial_private == SAMPLE_PRIVATE_KEY
        assert initial_public == SAMPLE_PUBLIC_KEY

        # Запустить watcher
        manager.start_watching()
        await asyncio.sleep(0.5)

        # Записать НЕВАЛИДНЫЕ ключи (не PEM формат)
        private_key_path.write_text("INVALID PRIVATE KEY CONTENT")
        public_key_path.write_text("INVALID PUBLIC KEY CONTENT")

        # Подождать попытку hot-reload
        await asyncio.sleep(3)

        # ВАЖНО: Старые ключи должны остаться доступными!
        # Graceful degradation - не заменяем ключи при ошибке
        current_private = manager.get_private_key_sync()
        current_public = manager.get_public_key_sync()

        # Старые валидные ключи должны быть сохранены
        assert current_private == SAMPLE_PRIVATE_KEY
        assert current_public == SAMPLE_PUBLIC_KEY

        # Остановить watcher
        await manager.stop_watching()


@pytest.mark.asyncio
async def test_missing_key_file_raises_error():
    """
    Тест что отсутствие ключей вызывает FileNotFoundError при инициализации.

    Проверяет:
    - Ошибка при отсутствии private key
    - Ошибка при отсутствии public key
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        non_existent_private = Path(tmpdir) / "missing_private.pem"
        non_existent_public = Path(tmpdir) / "missing_public.pem"

        # Попытка инициализации без файлов ключей должна raise FileNotFoundError
        with pytest.raises(FileNotFoundError):
            JWTKeyManager(
                private_key_path=str(non_existent_private),
                public_key_path=str(non_existent_public),
                enable_hot_reload=False
            )


@pytest.mark.asyncio
async def test_direct_pem_content_support():
    """
    Тест поддержки direct PEM content (для Kubernetes Secrets).

    Проверяет:
    - Manager может работать с direct PEM content вместо file paths
    - Hot-reload НЕ работает для direct PEM content (это нормально)
    """
    # Передаем direct PEM content вместо file paths
    manager = JWTKeyManager(
        private_key_path=SAMPLE_PRIVATE_KEY,  # Direct PEM content
        public_key_path=SAMPLE_PUBLIC_KEY,     # Direct PEM content
        enable_hot_reload=True  # Watcher не запустится для direct content
    )

    # Проверить что ключи загружены из direct content
    assert manager.get_private_key_sync() == SAMPLE_PRIVATE_KEY
    assert manager.get_public_key_sync() == SAMPLE_PUBLIC_KEY

    # Запуск watcher с direct content должен работать (но ничего не делать)
    manager.start_watching()
    await asyncio.sleep(0.5)
    await manager.stop_watching()
