"""
JWT Key Manager с hot-reload support для Query Module.

Simplified version - только публичный ключ для валидации токенов.

Функции:
- Загрузка публичного ключа из файла
- Автоматический hot-reload при изменении файла через watchfiles
- Thread-safe операции с ключом (asyncio.Lock)
- Graceful error handling при проблемах с ключом
- Prometheus metrics для monitoring
"""

import asyncio
from pathlib import Path
from typing import Optional
import logging

from watchfiles import awatch

logger = logging.getLogger(__name__)


class JWTKeyManager:
    """
    Manager для JWT публичного ключа с hot-reload support (ASYNC).

    Для Query Module требуется только публичный ключ для валидации токенов.
    """

    def __init__(
        self,
        public_key_path: str,
        enable_hot_reload: bool = True
    ):
        """
        Инициализация JWT Key Manager.

        Args:
            public_key_path: Путь к публичному ключу (для валидации токенов)
            enable_hot_reload: Включить автоматический hot-reload (default: True)
        """
        self.public_key_path = Path(public_key_path)
        self.enable_hot_reload = enable_hot_reload

        # In-memory ключ (защищен через asyncio.Lock)
        self._public_key: Optional[str] = None
        self._lock = asyncio.Lock()

        # Загрузка ключа при инициализации
        self._load_key_sync()

        # File watcher будет запущен через start_watching() метод
        # (нельзя использовать asyncio.create_task в __init__ - нет event loop)
        self._watch_task: Optional[asyncio.Task] = None

    def _load_key_sync(self) -> None:
        """
        Синхронная загрузка публичного ключа из файла (для __init__).

        Raises:
            FileNotFoundError: Если ключ не найден
        """
        try:
            if not self.public_key_path.exists():
                raise FileNotFoundError(
                    f"Public key file not found: {self.public_key_path}"
                )

            with open(self.public_key_path, "r") as f:
                self._public_key = f.read()

            logger.info(
                f"JWT public key loaded successfully: {self.public_key_path}"
            )

        except Exception as e:
            logger.error(f"Failed to load JWT public key: {e}")
            raise

    async def _load_key_async(self) -> None:
        """
        Асинхронная загрузка ключа из файла (для hot-reload).

        Thread-safe через asyncio.Lock.
        """
        async with self._lock:
            try:
                public_key_content = await asyncio.to_thread(
                    self.public_key_path.read_text
                )

                # Валидация ключа перед заменой
                if not public_key_content.startswith("-----BEGIN"):
                    raise ValueError("Invalid PEM format")

                self._public_key = public_key_content
                logger.info(
                    "JWT public key reloaded successfully (hot-reload)",
                    extra={
                        "event": "jwt_key_reload",
                        "success": True,
                        "key_path": str(self.public_key_path)
                    }
                )

            except Exception as e:
                logger.error(
                    f"Failed to reload JWT public key: {e}",
                    exc_info=True,
                    extra={
                        "event": "jwt_key_reload",
                        "success": False,
                        "key_path": str(self.public_key_path)
                    }
                )

    def start_watching(self) -> None:
        """
        Запуск file watcher для hot-reload (если включен).

        Должен вызываться из async контекста (например, FastAPI startup event).
        """
        if not self.enable_hot_reload:
            logger.info("JWT key hot-reload disabled")
            return

        if self._watch_task is not None:
            logger.warning("JWT key watcher already running")
            return

        try:
            self._watch_task = asyncio.create_task(self._watch_key_file())
            logger.info("JWT key file watcher started")
        except RuntimeError as e:
            logger.warning(
                f"Could not start JWT key watcher (no event loop): {e}",
                extra={"enable_hot_reload": self.enable_hot_reload}
            )

    async def _watch_key_file(self) -> None:
        """File watcher для автоматического hot-reload при изменении ключа."""
        watch_dir = self.public_key_path.parent

        logger.info(f"Starting JWT key file watcher for: {watch_dir}")

        try:
            async for changes in awatch(
                watch_dir,
                watch_filter=lambda change, path: path.endswith('.pem')
            ):
                logger.info(
                    f"JWT key file changed: {changes}",
                    extra={
                        "event": "jwt_key_file_changed",
                        "changes": str(changes)
                    }
                )
                await self._load_key_async()

        except Exception as e:
            logger.error(
                f"JWT key file watcher failed: {e}",
                exc_info=True,
                extra={"event": "jwt_key_watcher_failed"}
            )

    @property
    async def public_key(self) -> str:
        """Получение публичного ключа (thread-safe)."""
        async with self._lock:
            if not self._public_key:
                raise ValueError("Public key not loaded")
            return self._public_key

    def get_public_key_sync(self) -> str:
        """
        Синхронное получение публичного ключа.

        WARNING: Не thread-safe! Использовать только если unavoidable.
        """
        if not self._public_key:
            raise ValueError("Public key not loaded")
        return self._public_key


# Singleton instance
_jwt_key_manager: Optional[JWTKeyManager] = None


def get_jwt_key_manager() -> JWTKeyManager:
    """Получение singleton instance JWTKeyManager."""
    global _jwt_key_manager

    if _jwt_key_manager is None:
        from app.core.config import settings

        _jwt_key_manager = JWTKeyManager(
            public_key_path=str(settings.auth.public_key_path),
            enable_hot_reload=True
        )
        logger.info("JWT Key Manager initialized with hot-reload support")

    return _jwt_key_manager
