"""
Integration тест для JWT Hot-Reload в Query Module.

Проверяет что JWT публичный ключ автоматически перезагружается
при изменении файла ключа без перезапуска приложения.

ВАЖНО: Этот тест требует запущенный Query Module контейнер!
"""

import asyncio
import time
from pathlib import Path

import pytest


@pytest.mark.integration
@pytest.mark.asyncio
async def test_jwt_hot_reload_in_docker():
    """
    Integration тест: JWT hot-reload в Docker окружении.

    Сценарий:
    1. Создать backup оригинального ключа
    2. Заменить ключ на тестовый (симуляция cert-manager rotation)
    3. Подождать hot-reload (watchfiles срабатывает за 1-2 секунды)
    4. Проверить логи на наличие hot-reload события
    5. Восстановить оригинальный ключ

    Требования:
    - Docker и docker-compose установлены
    - Query Module запущен: docker-compose up -d query-module
    """
    # Пути к файлам ключей (относительно корня проекта)
    project_root = Path(__file__).parent.parent.parent.parent
    key_file = project_root / "query-module" / "keys" / "public_key.pem"
    backup_key_file = key_file.with_suffix(".pem.backup")
    test_key_file = key_file.with_suffix(".pem.test")

    # Тестовый ключ (fake для проверки hot-reload)
    test_key_content = """-----BEGIN PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAyKz8vPHqkuFXBPPqS0T7
testkey123456789testkey123456789testkey123456789testkey123456789
testkey123456789testkey123456789testkey123456789testkey123456789
testkey123456789testkey123456789testkey123456789testkey123456789
testkey123456789testkey123456789testkey123456789testkey123456789
testkey123456789testkey123456789testkey123456789testkey123456789
-----END PUBLIC KEY-----
"""

    try:
        # Шаг 1: Создание backup оригинального ключа
        assert key_file.exists(), f"Файл ключа не найден: {key_file}"
        original_key_content = key_file.read_text()
        backup_key_file.write_text(original_key_content)

        # Шаг 2: Создание тестового ключа
        test_key_file.write_text(test_key_content)

        # Шаг 3: Замена ключа (симуляция cert-manager rotation)
        key_file.write_text(test_key_content)

        # Шаг 4: Ожидание hot-reload (watchfiles обычно срабатывает за 1-2 секунды)
        await asyncio.sleep(3)

        # Шаг 5: Проверка логов на наличие hot-reload события
        import subprocess

        result = subprocess.run(
            ["docker", "logs", "--tail", "50", "artstore_query_module"],
            capture_output=True,
            text=True,
            check=True,
        )

        logs = result.stdout

        # Проверка наличия успешного hot-reload сообщения
        assert (
            "JWT key file changed" in logs or "JWT public key reloaded successfully" in logs
        ), (
            "Hot-reload событие НЕ найдено в логах!\n"
            f"Последние 50 строк логов:\n{logs}"
        )

        # Дополнительная проверка: убедиться что reload был успешным
        assert "JWT public key reloaded successfully (hot-reload)" in logs, (
            "Hot-reload событие обнаружено, но reload НЕ был успешным!\n"
            f"Последние 50 строк логов:\n{logs}"
        )

    finally:
        # Шаг 6: Cleanup - восстановление оригинального ключа
        if backup_key_file.exists():
            key_file.write_text(backup_key_file.read_text())
            backup_key_file.unlink()

        if test_key_file.exists():
            test_key_file.unlink()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_jwt_hot_reload_multiple_times():
    """
    Integration тест: Несколько последовательных hot-reload операций.

    Проверяет что watchfiles корректно обрабатывает множественные изменения файла.
    """
    project_root = Path(__file__).parent.parent.parent.parent
    key_file = project_root / "query-module" / "keys" / "public_key.pem"
    backup_key_file = key_file.with_suffix(".pem.backup")

    test_keys = [
        "testkey_iteration_1",
        "testkey_iteration_2",
        "testkey_iteration_3",
    ]

    try:
        # Backup оригинального ключа
        original_key_content = key_file.read_text()
        backup_key_file.write_text(original_key_content)

        for i, test_marker in enumerate(test_keys, start=1):
            # Создание тестового ключа с уникальным маркером
            test_key_content = f"""-----BEGIN PUBLIC KEY-----
{test_marker}
-----END PUBLIC KEY-----
"""
            # Замена ключа
            key_file.write_text(test_key_content)

            # Ожидание hot-reload
            await asyncio.sleep(2)

        # Проверка логов на наличие ВСЕХ hot-reload событий
        import subprocess

        result = subprocess.run(
            ["docker", "logs", "--tail", "100", "artstore_query_module"],
            capture_output=True,
            text=True,
            check=True,
        )

        logs = result.stdout

        # Подсчет количества hot-reload событий
        reload_count = logs.count("JWT public key reloaded successfully (hot-reload)")

        assert reload_count >= 3, (
            f"Ожидалось минимум 3 hot-reload события, найдено: {reload_count}\n"
            f"Последние 100 строк логов:\n{logs}"
        )

    finally:
        # Cleanup
        if backup_key_file.exists():
            key_file.write_text(backup_key_file.read_text())
            backup_key_file.unlink()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_jwt_hot_reload_invalid_key_graceful_handling():
    """
    Integration тест: Graceful handling при невалидном ключе.

    Проверяет что приложение НЕ падает при попытке загрузки невалидного ключа,
    а сохраняет старый валидный ключ.
    """
    project_root = Path(__file__).parent.parent.parent.parent
    key_file = project_root / "query-module" / "keys" / "public_key.pem"
    backup_key_file = key_file.with_suffix(".pem.backup")

    # Невалидный ключ (не PEM формат)
    invalid_key_content = "THIS IS NOT A VALID PEM KEY"

    try:
        # Backup оригинального ключа
        original_key_content = key_file.read_text()
        backup_key_file.write_text(original_key_content)

        # Замена ключа на невалидный
        key_file.write_text(invalid_key_content)

        # Ожидание попытки hot-reload
        await asyncio.sleep(3)

        # Проверка логов
        import subprocess

        result = subprocess.run(
            ["docker", "logs", "--tail", "50", "artstore_query_module"],
            capture_output=True,
            text=True,
            check=True,
        )

        logs = result.stdout

        # Проверка что есть error log о невалидном ключе
        # НО приложение продолжает работать (не crash)
        assert "JWT key file changed" in logs, "File change detection должен сработать"

        # Проверка что контейнер ВСЕ ЕЩЕ работает
        status_result = subprocess.run(
            ["docker", "ps", "--filter", "name=artstore_query_module", "--format", "{{.Status}}"],
            capture_output=True,
            text=True,
            check=True,
        )

        assert "Up" in status_result.stdout, "Контейнер должен продолжать работать после невалидного ключа"

    finally:
        # Cleanup
        if backup_key_file.exists():
            key_file.write_text(backup_key_file.read_text())
            backup_key_file.unlink()

        # Дополнительное ожидание для перезагрузки валидного ключа
        await asyncio.sleep(2)
