"""
JWT Key Manager с hot-reload support для Admin Module.

Dual-key version - приватный и публичный ключи для создания и валидации токенов.

Sprint: JWT Hot-Reload Implementation (2026-01-08)

Функции:
- Загрузка приватного и публичного ключей из файлов
- Автоматический hot-reload при изменении файлов через watchfiles
- Thread-safe операции с ключами (asyncio.Lock)
- Graceful error handling при проблемах с ключами
- Поддержка как файловых путей, так и direct PEM content

Особенности Admin Module:
- Dual-key system: private_key для создания токенов, public_key для валидации
- Поддержка legacy behavior: direct PEM content из Kubernetes Secrets
- Два независимых watcher'а для каждого ключа

Архитектурные требования:
- НЕ вызывать asyncio.create_task() в __init__ (нет event loop при инициализации singleton)
- Вместо этого использовать явный метод start_watching() в FastAPI startup event
"""

import asyncio
from pathlib import Path
from typing import Optional
import logging

from watchfiles import awatch

logger = logging.getLogger(__name__)


class JWTKeyManager:
    """
    Manager для JWT приватного и публичного ключей с hot-reload support (ASYNC).

    Для Admin Module требуются оба ключа:
    - Private key: для создания (signing) JWT токенов
    - Public key: для валидации токенов (в fallback режиме)
    """

    def __init__(
        self,
        private_key_path: str,
        public_key_path: str,
        enable_hot_reload: bool = True
    ):
        """
        Инициализация JWT Key Manager для Admin Module.

        Args:
            private_key_path: Путь к приватному ключу (для создания токенов)
            public_key_path: Путь к публичному ключу (для валидации токенов)
            enable_hot_reload: Включить автоматический hot-reload (default: True)
        """
        self.private_key_path = Path(private_key_path)
        self.public_key_path = Path(public_key_path)
        self.enable_hot_reload = enable_hot_reload

        # In-memory ключи (защищены через asyncio.Lock)
        self._private_key: Optional[str] = None
        self._public_key: Optional[str] = None
        self._lock = asyncio.Lock()

        # Watcher tasks (для graceful shutdown)
        self._private_watcher_task: Optional[asyncio.Task] = None
        self._public_watcher_task: Optional[asyncio.Task] = None

        # Загрузка ключей при инициализации
        self._load_keys_sync()

    def _is_direct_pem_content(self, content: str) -> bool:
        """
        Проверка является ли строка direct PEM content.

        Args:
            content: Строка для проверки

        Returns:
            True если это PEM content, False если это file path
        """
        return content.strip().startswith("-----BEGIN")

    def _load_keys_sync(self) -> None:
        """
        Синхронная загрузка ключей из файлов или direct PEM content (для __init__).

        Поддерживает два варианта:
        1. File path - путь к PEM файлу (традиционный способ)
        2. Direct PEM content - полное PEM содержимое (для Kubernetes Secrets)

        Raises:
            FileNotFoundError: Если ключи-файлы не найдены
        """
        try:
            # Загрузка private key
            private_key_value = str(self.private_key_path)

            if self._is_direct_pem_content(private_key_value):
                # Direct PEM content (из Kubernetes Secret или env variable)
                self._private_key = private_key_value
                logger.info("JWT private key loaded from direct PEM content")
            else:
                # File path (традиционный способ)
                if not self.private_key_path.exists():
                    raise FileNotFoundError(
                        f"Private key file not found: {self.private_key_path}"
                    )

                with open(self.private_key_path, "r") as f:
                    self._private_key = f.read()

                logger.info(f"JWT private key loaded successfully: {self.private_key_path}")

            # Загрузка public key
            public_key_value = str(self.public_key_path)

            if self._is_direct_pem_content(public_key_value):
                # Direct PEM content (из Kubernetes Secret или env variable)
                self._public_key = public_key_value
                logger.info("JWT public key loaded from direct PEM content")
            else:
                # File path (традиционный способ)
                if not self.public_key_path.exists():
                    raise FileNotFoundError(
                        f"Public key file not found: {self.public_key_path}"
                    )

                with open(self.public_key_path, "r") as f:
                    self._public_key = f.read()

                logger.info(f"JWT public key loaded successfully: {self.public_key_path}")

        except Exception as e:
            logger.error(f"Failed to load JWT keys: {e}")
            raise

    async def _load_keys_async(self) -> None:
        """
        Асинхронная загрузка ключей из файлов (для hot-reload).

        Thread-safe через asyncio.Lock.
        Только для file-based ключей (НЕ для direct PEM content).

        Graceful error handling:
        - Валидирует PEM формат перед заменой ключей
        - Сохраняет старые ключи при ошибках валидации
        - Не ломает приложение при невалидных ключах
        """
        async with self._lock:
            try:
                # Загрузка private key (с валидацией)
                if not self._is_direct_pem_content(str(self.private_key_path)):
                    private_key_content = await asyncio.to_thread(
                        self.private_key_path.read_text
                    )

                    # Валидация PEM формата перед заменой
                    if not self._is_direct_pem_content(private_key_content):
                        raise ValueError(
                            f"Invalid PEM format for private key: {self.private_key_path}"
                        )

                    # ✅ Только если валидация успешна - заменяем ключ
                    self._private_key = private_key_content
                    logger.info("JWT private key reloaded successfully (hot-reload)")

                # Загрузка public key (с валидацией)
                if not self._is_direct_pem_content(str(self.public_key_path)):
                    public_key_content = await asyncio.to_thread(
                        self.public_key_path.read_text
                    )

                    # Валидация PEM формата перед заменой
                    if not self._is_direct_pem_content(public_key_content):
                        raise ValueError(
                            f"Invalid PEM format for public key: {self.public_key_path}"
                        )

                    # ✅ Только если валидация успешна - заменяем ключ
                    self._public_key = public_key_content
                    logger.info("JWT public key reloaded successfully (hot-reload)")

            except Exception as e:
                # ❌ НЕ заменяем ключи при ошибке - оставляем старые (graceful degradation)
                logger.error(
                    f"Failed to reload JWT keys, keeping old keys: {e}",
                    exc_info=True
                )

    async def _watch_key_files(self) -> None:
        """
        File watcher для автоматического hot-reload при изменении ключей.

        Отслеживает изменения в директории с ключами и перезагружает оба ключа.
        """
        # Определяем директорию для watching (общая для обоих ключей)
        watch_dir = self.private_key_path.parent

        logger.info(f"Starting JWT key files watcher for: {watch_dir}")

        try:
            async for changes in awatch(
                watch_dir,
                watch_filter=lambda change, path: path.endswith('.pem')
            ):
                logger.info(f"JWT key files changed: {changes}")
                await self._load_keys_async()

        except Exception as e:
            logger.error(f"JWT key files watcher failed: {e}", exc_info=True)

    def start_watching(self) -> None:
        """
        Запуск file watcher для hot-reload.

        ДОЛЖЕН вызываться в FastAPI startup event, где уже есть running event loop.

        ВАЖНО: НЕ вызывать в __init__ (нет event loop при инициализации singleton)!
        """
        if not self.enable_hot_reload:
            logger.info("JWT hot-reload disabled by configuration")
            return

        # Проверка что мы в async context
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            logger.warning(
                "start_watching() called outside async context - "
                "watcher will not start. Call this method in FastAPI startup event."
            )
            return

        # Запуск watcher task
        self._private_watcher_task = asyncio.create_task(self._watch_key_files())
        logger.info("JWT key files watcher started successfully")

    async def stop_watching(self) -> None:
        """
        Остановка file watcher (для graceful shutdown).

        Вызывается в FastAPI shutdown event.
        """
        if self._private_watcher_task:
            self._private_watcher_task.cancel()
            try:
                await self._private_watcher_task
            except asyncio.CancelledError:
                pass
            logger.info("JWT key files watcher stopped")

    @property
    async def private_key(self) -> str:
        """Получение приватного ключа (thread-safe)."""
        async with self._lock:
            if not self._private_key:
                raise ValueError("Private key not loaded")
            return self._private_key

    @property
    async def public_key(self) -> str:
        """Получение публичного ключа (thread-safe)."""
        async with self._lock:
            if not self._public_key:
                raise ValueError("Public key not loaded")
            return self._public_key

    def get_private_key_sync(self) -> str:
        """
        Синхронное получение приватного ключа.

        WARNING: Не thread-safe! Использовать только если unavoidable.

        Используется в TokenService для создания токенов.
        """
        if not self._private_key:
            raise ValueError("Private key not loaded")
        return self._private_key

    def get_public_key_sync(self) -> str:
        """
        Синхронное получение публичного ключа.

        WARNING: Не thread-safe! Использовать только если unavoidable.

        Используется в TokenService для валидации токенов (fallback).
        """
        if not self._public_key:
            raise ValueError("Public key not loaded")
        return self._public_key


# Singleton instance
_jwt_key_manager: Optional[JWTKeyManager] = None


def get_jwt_key_manager() -> JWTKeyManager:
    """
    Получение singleton instance JWTKeyManager для Admin Module.

    Returns:
        JWTKeyManager: Singleton instance с dual-key support
    """
    global _jwt_key_manager

    if _jwt_key_manager is None:
        from app.core.config import settings

        _jwt_key_manager = JWTKeyManager(
            private_key_path=settings.jwt.private_key_path,
            public_key_path=settings.jwt.public_key_path,
            enable_hot_reload=True
        )
        logger.info("JWT Key Manager initialized with hot-reload support (dual-key)")

    return _jwt_key_manager
