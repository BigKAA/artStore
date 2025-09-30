#!/usr/bin/env python3
"""
Скрипт для генерации пары ключей JWT (RS256).

Этот скрипт создает приватный и публичный ключи RSA для подписи и верификации JWT токенов.
Ключи сохраняются в директорию ./keys/ в формате PEM.

Использование:
    python scripts/generate_jwt_keys.py
    python scripts/generate_jwt_keys.py --key-size 4096
    python scripts/generate_jwt_keys.py --output-dir ./custom-keys
"""

import argparse
import os
from pathlib import Path

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa


def generate_jwt_keys(
    output_dir: str = "./keys",
    key_size: int = 2048,
    private_key_filename: str = "jwt-private.pem",
    public_key_filename: str = "jwt-public.pem",
    force: bool = False
) -> None:
    """
    Генерирует пару ключей RSA для JWT аутентификации.

    Args:
        output_dir: Директория для сохранения ключей
        key_size: Размер ключа в битах (2048, 3072, 4096)
        private_key_filename: Имя файла приватного ключа
        public_key_filename: Имя файла публичного ключа
        force: Перезаписать существующие ключи
    """
    # Создаем директорию если не существует
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    private_key_path = output_path / private_key_filename
    public_key_path = output_path / public_key_filename

    # Проверяем существование ключей
    if not force and (private_key_path.exists() or public_key_path.exists()):
        print("⚠️  Предупреждение: Ключи уже существуют!")
        print(f"   Приватный ключ: {private_key_path}")
        print(f"   Публичный ключ: {public_key_path}")
        response = input("Перезаписать существующие ключи? (yes/no): ")
        if response.lower() not in ["yes", "y"]:
            print("❌ Генерация отменена")
            return

    print(f"🔑 Генерация пары ключей RSA ({key_size} бит)...")

    # Генерируем приватный ключ
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=key_size,
        backend=default_backend()
    )

    # Извлекаем публичный ключ
    public_key = private_key.public_key()

    # Сохраняем приватный ключ
    with open(private_key_path, "wb") as f:
        f.write(
            private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption()
            )
        )
    print(f"✅ Приватный ключ сохранен: {private_key_path}")

    # Сохраняем публичный ключ
    with open(public_key_path, "wb") as f:
        f.write(
            public_key.public_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PublicFormat.SubjectPublicKeyInfo
            )
        )
    print(f"✅ Публичный ключ сохранен: {public_key_path}")

    # Устанавливаем права доступа (только для Unix-подобных систем)
    if os.name != "nt":
        os.chmod(private_key_path, 0o600)  # Только владелец может читать
        os.chmod(public_key_path, 0o644)   # Все могут читать
        print("🔒 Установлены права доступа к файлам")

    print("✨ Генерация ключей завершена успешно!")
    print("\n📝 Следующие шаги:")
    print("   1. Убедитесь, что приватный ключ защищен и не добавлен в git")
    print("   2. Обновите config.yaml с путями к ключам:")
    print(f"      private_key_path: \"{private_key_path}\"")
    print(f"      public_key_path: \"{public_key_path}\"")
    print("   3. Распространите публичный ключ на другие микросервисы")


def main():
    """Точка входа скрипта."""
    parser = argparse.ArgumentParser(
        description="Генерация пары ключей RSA для JWT аутентификации"
    )
    parser.add_argument(
        "--output-dir",
        default="./keys",
        help="Директория для сохранения ключей (по умолчанию: ./keys)"
    )
    parser.add_argument(
        "--key-size",
        type=int,
        default=2048,
        choices=[2048, 3072, 4096],
        help="Размер ключа в битах (по умолчанию: 2048)"
    )
    parser.add_argument(
        "--private-key-name",
        default="jwt-private.pem",
        help="Имя файла приватного ключа (по умолчанию: jwt-private.pem)"
    )
    parser.add_argument(
        "--public-key-name",
        default="jwt-public.pem",
        help="Имя файла публичного ключа (по умолчанию: jwt-public.pem)"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Перезаписать существующие ключи без подтверждения"
    )

    args = parser.parse_args()

    try:
        generate_jwt_keys(
            output_dir=args.output_dir,
            key_size=args.key_size,
            private_key_filename=args.private_key_name,
            public_key_filename=args.public_key_name,
            force=args.force
        )
    except Exception as e:
        print(f"❌ Ошибка при генерации ключей: {e}")
        exit(1)


if __name__ == "__main__":
    main()
