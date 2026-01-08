"""
Standalone тест для JWT Hot-Reload в Admin Module.

Этот тест не зависит от pytest conftest и может выполняться независимо.

Sprint: JWT Hot-Reload Implementation (2026-01-08)
"""

import asyncio
from pathlib import Path
import tempfile
import sys

# Добавляем путь к модулю
sys.path.insert(0, str(Path(__file__).parent.parent))

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


async def test_initialization():
    """Тест инициализации JWTKeyManager с валидными ключами."""
    print("\n🧪 Test 1: Инициализация JWTKeyManager (dual-key)")

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

        # Проверить что ключи загружены
        private_key = manager.get_private_key_sync()
        public_key = manager.get_public_key_sync()

        assert private_key == SAMPLE_PRIVATE_KEY, "Private key не совпадает"
        assert public_key == SAMPLE_PUBLIC_KEY, "Public key не совпадает"

        print("✅ PASSED: Ключи успешно загружены")


async def test_hot_reload():
    """Тест автоматического hot-reload при изменении файлов."""
    print("\n🧪 Test 2: Hot-reload при изменении файлов")

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
        print("  ✓ Начальные ключи загружены")

        # Запустить watcher
        manager.start_watching()
        print("  ✓ Watcher запущен")

        # Подождать запуска watcher
        await asyncio.sleep(0.5)

        # Изменить ключи
        print("  ℹ️  Изменяю файлы ключей...")
        private_key_path.write_text(UPDATED_PRIVATE_KEY)
        public_key_path.write_text(UPDATED_PUBLIC_KEY)

        # Подождать hot-reload
        print("  ⏳ Жду hot-reload (3 секунды)...")
        await asyncio.sleep(3)

        # Проверить что ключи обновились
        new_private = manager.get_private_key_sync()
        new_public = manager.get_public_key_sync()

        assert new_private == UPDATED_PRIVATE_KEY, "Private key не обновился"
        assert new_public == UPDATED_PUBLIC_KEY, "Public key не обновился"

        print("✅ PASSED: Ключи автоматически перезагружены")

        # Остановить watcher
        await manager.stop_watching()
        print("  ✓ Watcher остановлен")


async def test_concurrent_access():
    """Тест thread-safety при конкурентном доступе."""
    print("\n🧪 Test 3: Thread-safety при конкурентном доступе")

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
        print("  ⏳ Выполняю 50 конкурентных чтений (5 задач × 10 итераций)...")
        tasks = [read_keys_multiple_times() for _ in range(5)]
        await asyncio.gather(*tasks)

        print("✅ PASSED: Thread-safety работает корректно")


async def test_graceful_error_handling():
    """Тест graceful error handling при невалидных ключах."""
    print("\n🧪 Test 4: Graceful error handling при невалидных ключах")

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
        print("  ✓ Начальные валидные ключи загружены")

        # Запустить watcher
        manager.start_watching()
        await asyncio.sleep(0.5)

        # Записать НЕВАЛИДНЫЕ ключи
        print("  ℹ️  Записываю невалидные ключи...")
        private_key_path.write_text("INVALID PRIVATE KEY")
        public_key_path.write_text("INVALID PUBLIC KEY")

        # Подождать попытку hot-reload
        await asyncio.sleep(3)

        # Проверить что старые ключи сохранены (graceful degradation)
        current_private = manager.get_private_key_sync()
        current_public = manager.get_public_key_sync()

        assert current_private == SAMPLE_PRIVATE_KEY, "Старый private key не сохранен"
        assert current_public == SAMPLE_PUBLIC_KEY, "Старый public key не сохранен"

        print("✅ PASSED: Graceful degradation работает - старые ключи сохранены")

        # Остановить watcher
        await manager.stop_watching()


async def main():
    """Запуск всех тестов."""
    print("=" * 60)
    print("JWT Hot-Reload Testing для Admin Module")
    print("Sprint: JWT Hot-Reload Implementation (2026-01-08)")
    print("=" * 60)

    try:
        await test_initialization()
        await test_hot_reload()
        await test_concurrent_access()
        await test_graceful_error_handling()

        print("\n" + "=" * 60)
        print("✅ ВСЕ ТЕСТЫ ПРОЙДЕНЫ УСПЕШНО!")
        print("=" * 60)
        return 0

    except AssertionError as e:
        print(f"\n❌ ТЕСТ ПРОВАЛЕН: {e}")
        return 1
    except Exception as e:
        print(f"\n❌ ОШИБКА: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)
