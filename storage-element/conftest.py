"""
Pytest Configuration для Storage Element Tests.

Global fixtures и настройка для unit и integration tests.
"""

import os
from pathlib import Path

import pytest

# ВАЖНО: Установить JWT_PUBLIC_KEY_PATH ДО импорта app modules
# иначе settings будут загружены без ключа
project_root = Path(__file__).parent.parent
public_key_path = project_root / "admin-module" / ".keys" / "public_key.pem"
os.environ["JWT_PUBLIC_KEY_PATH"] = str(public_key_path)
