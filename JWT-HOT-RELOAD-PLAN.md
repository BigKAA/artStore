# JWT Hot-Reload Implementation Plan

## 📋 Обзор

План обновления всех модулей для поддержки hot-reload JWT ключей из файлов с использованием cert-manager в Kubernetes.

**Цель**: Zero-downtime rotation JWT ключей через cert-manager с автоматическим hot-reload без перезапуска подов.

**Ключевые требования**:
- ✅ Автоматическая подгрузка ключей при изменении файлов
- ✅ Graceful transition период для старых токенов
- ✅ Thread-safe операции с ключами
- ✅ Обратная совместимость с текущей реализацией
- ✅ Минимальные изменения в существующем коде

---

## 🏗️ Архитектурный обзор

### Текущее состояние

| Модуль | Источник ключей | Hot-reload | Примечания |
|--------|----------------|------------|------------|
| **Admin Module** | Файлы или PEM content через config | ❌ | Загрузка один раз в `TokenService.__init__()` |
| **Ingester Module** | Файл `/app/keys/public_key.pem` | ❌ | Загрузка через `AuthSettings.public_key_path` |
| **Query Module** | Файл `/app/keys/public_key.pem` | ❌ | Загрузка через `AuthSettings.public_key_path` |
| **Storage Element** | Нет JWT | N/A | Не использует JWT аутентификацию |

### Целевая архитектура

| Модуль | Источник ключей | Hot-reload | Механизм |
|--------|----------------|------------|----------|
| **Admin Module** | Файлы `/app/keys/*.pem` | ✅ | `JWTKeyManager` с watchfiles |
| **Ingester Module** | Файл `/app/keys/public_key.pem` | ✅ | `JWTKeyManager` с watchfiles |
| **Query Module** | Файл `/app/keys/public_key.pem` | ✅ | `JWTKeyManager` с watchfiles |
| **Storage Element** | N/A | N/A | Без изменений |

---

## 📦 Компоненты для реализации

### 1. Базовый класс `JWTKeyManager`

**Общий класс для всех модулей** с функционалом:
- Загрузка ключей из файлов при инициализации
- Автоматический file watching через `watchfiles`
- Thread-safe hot-reload при изменении файлов
- Graceful error handling при ошибках загрузки
- Метрики и логирование для observability

**Расположение**: Создать общий пакет `common/jwt_manager.py` или реализовать в каждом модуле отдельно.

**Зависимости**:
```python
# requirements.txt дополнение
watchfiles==0.21.0  # File system watching
```

---

## 🔧 Детальный план по модулям

---

## 1️⃣ Admin Module

### Текущая реализация

**Файл**: `admin-module/app/services/token_service.py`

**Проблема**: Ключи загружаются один раз в `__init__`:
```python
class TokenService:
    def __init__(self):
        self._private_key: Optional[str] = None
        self._public_key: Optional[str] = None
        self._load_keys()  # ❌ Загрузка ТОЛЬКО при инициализации
```

### Предлагаемые изменения

#### Шаг 1.1: Создать `JWTKeyManager` для Admin Module

**Новый файл**: `admin-module/app/core/jwt_key_manager.py`

```python
"""
JWT Key Manager с hot-reload support для Admin Module.

Функции:
- Загрузка приватного и публичного ключей из файлов
- Автоматический hot-reload при изменении файлов через watchfiles
- Thread-safe операции с ключами (asyncio.Lock)
- Graceful error handling при проблемах с ключами
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
    Manager для JWT ключей с hot-reload support (ASYNC).

    Features:
    - Загрузка ключей из файлов при инициализации
    - Автоматический reload при изменении файлов
    - Thread-safe операции через asyncio.Lock
    - Metrics для monitoring (rotation events, reload latency)

    ВАЖНО: Для Admin Module требуются оба ключа (private + public).
    """

    def __init__(
        self,
        private_key_path: str,
        public_key_path: str,
        enable_hot_reload: bool = True
    ):
        """
        Инициализация JWT Key Manager.

        Args:
            private_key_path: Путь к приватному ключу (для подписи токенов)
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

        # Загрузка ключей при инициализации
        self._load_keys_sync()

        # Запуск file watcher (если hot-reload включен)
        if self.enable_hot_reload:
            asyncio.create_task(self._watch_key_files())

    def _load_keys_sync(self) -> None:
        """
        Синхронная загрузка ключей из файлов (для __init__).

        Raises:
            FileNotFoundError: Если ключи не найдены
            ValueError: Если ключи повреждены
        """
        try:
            # Загрузка приватного ключа
            if not self.private_key_path.exists():
                raise FileNotFoundError(
                    f"Private key file not found: {self.private_key_path}"
                )

            with open(self.private_key_path, "r") as f:
                self._private_key = f.read()

            # Загрузка публичного ключа
            if not self.public_key_path.exists():
                raise FileNotFoundError(
                    f"Public key file not found: {self.public_key_path}"
                )

            with open(self.public_key_path, "r") as f:
                self._public_key = f.read()

            logger.info(
                "JWT keys loaded successfully "
                f"(private: {self.private_key_path}, public: {self.public_key_path})"
            )

        except Exception as e:
            logger.error(f"Failed to load JWT keys: {e}")
            raise

    async def _load_keys_async(self) -> None:
        """
        Асинхронная загрузка ключей из файлов (для hot-reload).

        Thread-safe через asyncio.Lock.
        """
        async with self._lock:
            try:
                # Асинхронное чтение файлов
                private_key_content = await asyncio.to_thread(
                    self.private_key_path.read_text
                )
                public_key_content = await asyncio.to_thread(
                    self.public_key_path.read_text
                )

                # Atomic update обоих ключей
                self._private_key = private_key_content
                self._public_key = public_key_content

                logger.info("JWT keys reloaded successfully (hot-reload)")

                # TODO: Добавить Prometheus метрику для hot-reload event
                # record_jwt_keys_reload(success=True)

            except Exception as e:
                logger.error(f"Failed to reload JWT keys: {e}", exc_info=True)
                # TODO: Добавить Prometheus метрику для failed reload
                # record_jwt_keys_reload(success=False, error=str(e))

    async def _watch_key_files(self) -> None:
        """
        File watcher для автоматического hot-reload при изменении ключей.

        Использует watchfiles (async inotify wrapper) для мониторинга
        изменений в директории ключей.
        """
        watch_dir = self.private_key_path.parent

        logger.info(f"Starting JWT key file watcher for directory: {watch_dir}")

        try:
            async for changes in awatch(
                watch_dir,
                watch_filter=lambda change, path: path.endswith('.pem')
            ):
                logger.info(f"JWT key files changed: {changes}")

                # Reload ключей при изменении
                await self._load_keys_async()

        except Exception as e:
            logger.error(f"JWT key file watcher failed: {e}", exc_info=True)

    @property
    async def private_key(self) -> str:
        """
        Получение приватного ключа (thread-safe).

        Returns:
            str: PEM-encoded приватный ключ

        Raises:
            ValueError: Если ключ не загружен
        """
        async with self._lock:
            if not self._private_key:
                raise ValueError("Private key not loaded")
            return self._private_key

    @property
    async def public_key(self) -> str:
        """
        Получение публичного ключа (thread-safe).

        Returns:
            str: PEM-encoded публичный ключ

        Raises:
            ValueError: Если ключ не загружен
        """
        async with self._lock:
            if not self._public_key:
                raise ValueError("Public key not loaded")
            return self._public_key

    def get_private_key_sync(self) -> str:
        """
        Синхронное получение приватного ключа (для sync кода).

        WARNING: Не thread-safe! Использовать только если unavoidable.

        Returns:
            str: PEM-encoded приватный ключ
        """
        if not self._private_key:
            raise ValueError("Private key not loaded")
        return self._private_key

    def get_public_key_sync(self) -> str:
        """
        Синхронное получение публичного ключа (для sync кода).

        WARNING: Не thread-safe! Использовать только если unavoidable.

        Returns:
            str: PEM-encoded публичный ключ
        """
        if not self._public_key:
            raise ValueError("Public key not loaded")
        return self._public_key


# Singleton instance
_jwt_key_manager: Optional[JWTKeyManager] = None


def get_jwt_key_manager() -> JWTKeyManager:
    """
    Получение singleton instance JWTKeyManager.

    Returns:
        JWTKeyManager: Global key manager instance
    """
    global _jwt_key_manager

    if _jwt_key_manager is None:
        from app.core.config import settings

        _jwt_key_manager = JWTKeyManager(
            private_key_path=settings.jwt.private_key_path,
            public_key_path=settings.jwt.public_key_path,
            enable_hot_reload=True
        )
        logger.info("JWT Key Manager initialized with hot-reload support")

    return _jwt_key_manager
```

#### Шаг 1.2: Обновить `TokenService` для использования `JWTKeyManager`

**Файл**: `admin-module/app/services/token_service.py`

**Изменения**:

```python
# БЫЛО (строки 35-98):
class TokenService:
    def __init__(self):
        self._private_key: Optional[str] = None
        self._public_key: Optional[str] = None
        self._load_keys()

    def _load_keys(self) -> None:
        # ... сложная логика загрузки из файлов ...

# СТАНЕТ:
from app.core.jwt_key_manager import get_jwt_key_manager

class TokenService:
    def __init__(self):
        """Инициализация сервиса токенов с hot-reload support."""
        self._key_manager = get_jwt_key_manager()

    # Убрать метод _load_keys() полностью

    # Обновить все места использования ключей:

    # БЫЛО:
    def create_token_from_data(self, data: Dict, expires_delta: timedelta, ...) -> str:
        if not self._private_key:
            raise ValueError("No private key available")

        token = jwt.encode(claims, self._private_key, ...)

    # СТАНЕТ:
    def create_token_from_data(self, data: Dict, expires_delta: timedelta, ...) -> str:
        private_key = self._key_manager.get_private_key_sync()
        token = jwt.encode(claims, private_key, ...)

    # Аналогично для decode_token и других методов:
    # БЫЛО: self._public_key
    # СТАНЕТ: self._key_manager.get_public_key_sync()
```

#### Шаг 1.3: Обновить конфигурацию для унификации с другими модулями

**Файл**: `admin-module/app/core/config.py`

**Изменения**:

```python
class JWTSettings(BaseSettings):
    # ИЗМЕНИТЬ default пути для совместимости с cert-manager:

    # БЫЛО:
    private_key_path: str = Field(default=".keys/private_key.pem", ...)
    public_key_path: str = Field(default=".keys/public_key.pem", ...)

    # СТАНЕТ:
    private_key_path: str = Field(
        default="/app/keys/private_key.pem",  # ✅ Унифицировано с Ingester/Query
        alias="JWT_PRIVATE_KEY_PATH"
    )
    public_key_path: str = Field(
        default="/app/keys/public_key.pem",  # ✅ Унифицировано с Ingester/Query
        alias="JWT_PUBLIC_KEY_PATH"
    )

    # УДАЛИТЬ валидаторы load_private_key_from_provider и load_public_key_from_provider
    # (они больше не нужны - JWTKeyManager работает напрямую с файлами)
```

#### Шаг 1.4: Добавить зависимости

**Файл**: `admin-module/requirements.txt`

```txt
# Добавить:
watchfiles==0.21.0  # File system watching для hot-reload
```

---

## 2️⃣ Ingester Module

### Текущая реализация

**Файл**: `ingester-module/app/core/config.py`

**Статус**: Уже использует файловый подход ✅
```python
class AuthSettings(BaseSettings):
    public_key_path: Path = Field(
        default=Path("/app/keys/public_key.pem"),
        description="Путь к публичному ключу для валидации JWT токенов (RS256)",
    )
```

**Проблема**: Ключ загружается один раз, нет hot-reload.

### Предлагаемые изменения

#### Шаг 2.1: Создать `JWTKeyManager` для Ingester Module

**Новый файл**: `ingester-module/app/core/jwt_key_manager.py`

```python
"""
JWT Key Manager с hot-reload support для Ingester Module.

Simplified version - только публичный ключ для валидации токенов.
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

    Для Ingester Module требуется только публичный ключ для валидации токенов.
    """

    def __init__(self, public_key_path: str, enable_hot_reload: bool = True):
        """
        Инициализация JWT Key Manager.

        Args:
            public_key_path: Путь к публичному ключу
            enable_hot_reload: Включить автоматический hot-reload (default: True)
        """
        self.public_key_path = Path(public_key_path)
        self.enable_hot_reload = enable_hot_reload

        # In-memory ключ (защищен через asyncio.Lock)
        self._public_key: Optional[str] = None
        self._lock = asyncio.Lock()

        # Загрузка ключа при инициализации
        self._load_key_sync()

        # Запуск file watcher (если hot-reload включен)
        if self.enable_hot_reload:
            asyncio.create_task(self._watch_key_file())

    def _load_key_sync(self) -> None:
        """
        Синхронная загрузка публичного ключа из файла (для __init__).

        Raises:
            FileNotFoundError: Если ключ не найден
        """
        if not self.public_key_path.exists():
            raise FileNotFoundError(
                f"Public key file not found: {self.public_key_path}"
            )

        with open(self.public_key_path, "r") as f:
            self._public_key = f.read()

        logger.info(f"JWT public key loaded successfully: {self.public_key_path}")

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

                self._public_key = public_key_content
                logger.info("JWT public key reloaded successfully (hot-reload)")

            except Exception as e:
                logger.error(f"Failed to reload JWT public key: {e}", exc_info=True)

    async def _watch_key_file(self) -> None:
        """File watcher для автоматического hot-reload при изменении ключа."""
        watch_dir = self.public_key_path.parent

        logger.info(f"Starting JWT key file watcher for: {watch_dir}")

        try:
            async for changes in awatch(
                watch_dir,
                watch_filter=lambda change, path: path.endswith('.pem')
            ):
                logger.info(f"JWT key file changed: {changes}")
                await self._load_key_async()

        except Exception as e:
            logger.error(f"JWT key file watcher failed: {e}", exc_info=True)

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
```

#### Шаг 2.2: Обновить JWT dependency для FastAPI

**Файл**: `ingester-module/app/api/dependencies.py` (или где используется JWT)

**Найти текущее использование public_key** и обновить:

```python
# БЫЛО (примерно):
from app.core.config import settings

def get_current_user(token: str = Depends(oauth2_scheme)):
    payload = jwt.decode(
        token,
        settings.auth.public_key_path.read_text(),  # ❌ Читает при каждом запросе!
        algorithms=[settings.auth.algorithm]
    )

# СТАНЕТ:
from app.core.jwt_key_manager import get_jwt_key_manager

jwt_key_manager = get_jwt_key_manager()

def get_current_user(token: str = Depends(oauth2_scheme)):
    payload = jwt.decode(
        token,
        jwt_key_manager.get_public_key_sync(),  # ✅ Использует in-memory cached key
        algorithms=[settings.auth.algorithm]
    )
```

#### Шаг 2.3: Добавить зависимости

**Файл**: `ingester-module/requirements.txt`

```txt
# Добавить:
watchfiles==0.21.0  # File system watching для hot-reload
```

---

## 3️⃣ Query Module

### Предлагаемые изменения

**Идентичны Ingester Module** - скопировать подход:

1. Создать `query-module/app/core/jwt_key_manager.py` (идентично Ingester)
2. Обновить использование в dependencies/auth middleware
3. Добавить `watchfiles==0.21.0` в requirements.txt

---

## 🧪 Тестирование hot-reload

### Unit тесты

**Файл**: `<module>/tests/unit/test_jwt_key_manager.py`

```python
"""
Unit тесты для JWTKeyManager hot-reload функционала.
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
    # TODO: Создать временные файлы ключей
    # TODO: Проверить что ключи загружены
    pass


@pytest.mark.asyncio
async def test_hot_reload_on_file_change():
    """Тест автоматического hot-reload при изменении файла ключа."""
    with tempfile.TemporaryDirectory() as tmpdir:
        key_path = Path(tmpdir) / "public_key.pem"

        # Создать начальный ключ
        initial_key = "-----BEGIN PUBLIC KEY-----\nINITIAL\n-----END PUBLIC KEY-----"
        key_path.write_text(initial_key)

        # Инициализировать manager
        manager = JWTKeyManager(
            public_key_path=str(key_path),
            enable_hot_reload=True
        )

        # Проверить начальное значение
        assert manager.get_public_key_sync() == initial_key

        # Изменить ключ
        updated_key = "-----BEGIN PUBLIC KEY-----\nUPDATED\n-----END PUBLIC KEY-----"
        await asyncio.sleep(0.5)  # Дать время watcher'у запуститься
        key_path.write_text(updated_key)

        # Подождать hot-reload (watchfiles обычно реагирует за <1s)
        await asyncio.sleep(2)

        # Проверить что ключ обновился
        assert manager.get_public_key_sync() == updated_key


@pytest.mark.asyncio
async def test_concurrent_key_access():
    """Тест thread-safety при конкурентном доступе к ключам."""
    # TODO: Параллельные чтения ключа во время hot-reload
    pass
```

### Integration тесты

**Файл**: `<module>/tests/integration/test_jwt_hot_reload.py`

```python
"""
Integration тесты для JWT hot-reload в реальном окружении.
"""

import pytest
import asyncio
from pathlib import Path

from app.core.jwt_key_manager import get_jwt_key_manager
from app.services.token_service import token_service  # Admin Module


@pytest.mark.integration
@pytest.mark.asyncio
async def test_token_validation_after_key_rotation():
    """
    Тест валидации токенов после ротации ключей.

    Сценарий:
    1. Создать токен со старым ключом
    2. Изменить ключ (симуляция cert-manager rotation)
    3. Проверить что старый токен НЕ валидируется новым ключом
    4. Создать токен с новым ключом
    5. Проверить что новый токен валидируется
    """
    # TODO: Реализовать end-to-end тест ротации
    pass
```

---

## 📊 Метрики и мониторинг

### Prometheus метрики для hot-reload

**Добавить в `<module>/app/core/metrics.py`**:

```python
from prometheus_client import Counter, Gauge, Histogram

# JWT key reload events
jwt_key_reload_total = Counter(
    "jwt_key_reload_total",
    "Total number of JWT key reload attempts",
    ["status"]  # success | failed
)

# JWT key reload latency
jwt_key_reload_duration_seconds = Histogram(
    "jwt_key_reload_duration_seconds",
    "Time taken to reload JWT keys",
    buckets=[0.01, 0.05, 0.1, 0.5, 1.0, 2.0, 5.0]
)

# Current key age
jwt_key_age_seconds = Gauge(
    "jwt_key_age_seconds",
    "Time since last JWT key reload"
)


def record_jwt_keys_reload(success: bool, error: str = None):
    """Запись метрики hot-reload события."""
    status = "success" if success else "failed"
    jwt_key_reload_total.labels(status=status).inc()
```

### Логирование

**Формат логов при hot-reload**:

```json
{
  "timestamp": "2025-01-07T12:34:56.789Z",
  "level": "INFO",
  "module": "jwt_key_manager",
  "message": "JWT keys reloaded successfully (hot-reload)",
  "extra": {
    "event": "jwt_key_reload",
    "success": true,
    "latency_ms": 45,
    "trigger": "file_change",
    "changed_files": ["/app/keys/public_key.pem"]
  }
}
```

---

## 🚀 План внедрения (Rollout Plan)

### Phase 1: Development (неделя 1)

**Задачи**:
- [ ] Создать `JWTKeyManager` для Admin Module
- [ ] Обновить `TokenService` для использования manager
- [ ] Написать unit тесты для hot-reload
- [ ] Локальное тестирование с manual file changes

**Критерии успеха**:
- ✅ Unit тесты проходят
- ✅ Локально можно изменить ключ и увидеть reload в логах

### Phase 2: Ingester & Query Modules (неделя 1-2)

**Задачи**:
- [ ] Создать `JWTKeyManager` для Ingester Module
- [ ] Создать `JWTKeyManager` для Query Module
- [ ] Обновить FastAPI dependencies
- [ ] Integration тесты для всех модулей

**Критерии успеха**:
- ✅ Integration тесты проходят
- ✅ Все модули используют hot-reload

### Phase 3: Docker Testing (неделя 2)

**Задачи**:
- [ ] Обновить docker-compose.yml для монтирования ключей
- [ ] Тестирование в Docker окружении
- [ ] Симуляция cert-manager rotation (manual file updates в volume)

**Тестовый сценарий**:
```bash
# 1. Запустить все модули через docker-compose
docker-compose up -d

# 2. Получить токен с текущим ключом
TOKEN=$(curl -X POST http://localhost:8000/api/auth/token ...)

# 3. Проверить что токен валидируется
curl -H "Authorization: Bearer $TOKEN" http://localhost:8020/api/v1/upload/init

# 4. Обновить ключ в volume (симуляция cert-manager)
docker cp new_public_key.pem artstore_ingester:/app/keys/public_key.pem

# 5. Подождать hot-reload (1-2 секунды)
sleep 2

# 6. Проверить логи hot-reload
docker logs artstore_ingester | grep "JWT keys reloaded"

# 7. Получить новый токен
NEW_TOKEN=$(curl -X POST http://localhost:8000/api/auth/token ...)

# 8. Проверить что новый токен валидируется
curl -H "Authorization: Bearer $NEW_TOKEN" http://localhost:8020/api/v1/upload/init
```

**Критерии успеха**:
- ✅ Hot-reload срабатывает в Docker
- ✅ Новые токены валидируются после rotation
- ✅ Нет downtime при rotation

### Phase 4: Kubernetes Integration (неделя 3)

**Задачи**:
- [ ] Настроить cert-manager в K8s кластере
- [ ] Создать Certificate манифесты для JWT ключей
- [ ] Обновить Deployments с init containers
- [ ] End-to-end тестирование с cert-manager rotation

**Критерии успеха**:
- ✅ cert-manager автоматически ротирует ключи
- ✅ Модули подхватывают новые ключи через hot-reload
- ✅ Zero-downtime rotation работает

### Phase 5: Production Rollout (неделя 4)

**Задачи**:
- [ ] Canary deployment (10% traffic)
- [ ] Мониторинг метрик hot-reload
- [ ] Gradual rollout (50% → 100%)
- [ ] Документация для ops команды

**Критерии успеха**:
- ✅ Нет errors в production
- ✅ Hot-reload метрики в норме
- ✅ Ops команда обучена

---

## 🔐 Security Considerations

### 1. File Permissions

**ВАЖНО**: Ключи должны иметь правильные permissions в Kubernetes:

```yaml
# Deployment с init container
initContainers:
  - name: prepare-keys
    command:
      - sh
      - -c
      - |
        chmod 600 /keys/private_key.pem  # ✅ Только владелец может читать
        chmod 644 /keys/public_key.pem   # ✅ Публичный ключ доступен для чтения
```

### 2. Graceful Error Handling

**Сценарий**: Что если новый ключ поврежден?

```python
async def _load_key_async(self) -> None:
    async with self._lock:
        try:
            new_key = await asyncio.to_thread(self.public_key_path.read_text)

            # Валидация ключа перед заменой
            if not new_key.startswith("-----BEGIN"):
                raise ValueError("Invalid PEM format")

            # ✅ Только если валидация успешна - заменяем ключ
            self._public_key = new_key

        except Exception as e:
            # ❌ НЕ заменяем ключ при ошибке - оставляем старый
            logger.error(f"Failed to reload key, keeping old key: {e}")
```

### 3. Audit Logging

Все hot-reload события должны логироваться в audit log:

```python
logger.info(
    "JWT key reloaded",
    extra={
        "event": "jwt_key_reload",
        "user": "system",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "success": True,
        "previous_key_age_hours": 23.5
    }
)
```

---

## 📝 Обратная совместимость

### Поддержка старого подхода

Для плавной миграции, `JWTKeyManager` должен поддерживать:

1. **Файловый источник** (новый подход) - `/app/keys/*.pem`
2. **Environment variables** (legacy) - `JWT_PRIVATE_KEY`, `JWT_PUBLIC_KEY`
3. **Direct PEM content** (legacy Kubernetes Secrets)

```python
class JWTKeyManager:
    def __init__(self, ...):
        # Попытка 1: Прочитать из файла
        if self.public_key_path.exists():
            self._load_from_file()
        # Попытка 2: Fallback на environment variable
        elif os.getenv("JWT_PUBLIC_KEY"):
            self._load_from_env()
        else:
            raise ValueError("No JWT key source available")
```

---

## ✅ Чеклист готовности к production

### Перед деплоем в production проверить:

- [ ] **Unit тесты**: Все hot-reload тесты проходят
- [ ] **Integration тесты**: End-to-end rotation сценарий работает
- [ ] **Метрики**: Prometheus метрики добавлены и работают
- [ ] **Логирование**: Audit logs для всех hot-reload событий
- [ ] **Документация**: Runbook для ops команды обновлен
- [ ] **Rollback план**: Процедура возврата к старым ключам
- [ ] **Monitoring**: Alerts настроены для failed hot-reload
- [ ] **Security**: File permissions проверены
- [ ] **Performance**: Latency hot-reload < 1s

---

## 📚 Дополнительные ресурсы

### Зависимости

- **watchfiles**: https://github.com/samuelcolvin/watchfiles
  - Async file system watching (использует Rust для performance)
  - Поддерживает inotify (Linux), FSEvents (macOS), ReadDirectoryChangesW (Windows)

### Альтернативные подходы

**Если watchfiles не подходит**:

1. **Polling approach** (менее эффективный):
```python
async def _poll_key_files(self):
    while True:
        await asyncio.sleep(5)  # Проверка каждые 5 секунд
        if self._file_modified():
            await self._load_key_async()
```

2. **Signal-based reload** (требует external trigger):
```python
# Reload по SIGHUP signal
signal.signal(signal.SIGHUP, lambda sig, frame: self._load_key_async())
```

---

## 🎯 Заключение

Этот план обеспечивает:

✅ **Zero-downtime rotation** JWT ключей через cert-manager
✅ **Автоматический hot-reload** во всех модулях без restart
✅ **Production-ready** с метриками, логированием, error handling
✅ **Обратная совместимость** с текущей реализацией
✅ **Полное тестирование** на всех уровнях (unit, integration, e2e)

**Следующий шаг**: Начать реализацию с Admin Module (Phase 1).
