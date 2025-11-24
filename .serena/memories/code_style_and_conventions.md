# Стиль кода и конвенции ArtStore

## Общие правила

- **Язык комментариев**: Русский язык
- **Язык документации**: Русский язык
- **Naming conventions**: Следовать стандартам языка (Python PEP 8)
- **Тестирование**: TDD подход, тесты пишутся перед кодом

## Python Code Style

### Naming Conventions
```python
# Modules: lowercase с underscores
# my_module.py

# Classes: CamelCase
class ServiceAccount:
    pass

# Functions/Methods: lowercase с underscores
def get_user_data():
    pass

# Constants: UPPERCASE с underscores
MAX_FILE_SIZE = 1024 * 1024

# Private members: leading underscore
def _internal_method():
    pass

# Variables: lowercase с underscores
user_count = 0
```

### Type Hints
Обязательны для всех функций и методов:
```python
def process_file(file_id: str, user_id: int) -> dict[str, Any]:
    """Обработка файла с заданным ID."""
    pass

async def fetch_data(url: str) -> Optional[dict]:
    """Асинхронная загрузка данных."""
    pass
```

### Docstrings
Обязательны для всех публичных функций, классов и модулей:
```python
def calculate_checksum(file_path: str) -> str:
    """
    Вычисляет SHA-256 checksum файла.
    
    Args:
        file_path: Путь к файлу для вычисления checksum
        
    Returns:
        Строка с hex представлением checksum
        
    Raises:
        FileNotFoundError: Если файл не найден
        IOError: При ошибке чтения файла
    """
    pass
```

### Async/Await
- Используется async/await для всех I/O операций
- Предпочтителен asyncio для concurrency
- PostgreSQL операции через asyncpg (async)
- Redis операции через redis-py (sync) для Service Discovery

```python
# ✅ Правильно
async def get_user(user_id: int) -> Optional[User]:
    async with db.session() as session:
        result = await session.execute(
            select(User).where(User.id == user_id)
        )
        return result.scalar_one_or_none()

# ❌ Неправильно - синхронный код в async функции
async def get_user(user_id: int) -> Optional[User]:
    session = db.session()  # Blocking!
    return session.query(User).get(user_id)
```

### Error Handling
```python
# Конкретные исключения
try:
    data = await fetch_data(url)
except httpx.HTTPError as e:
    logger.error(f"HTTP error: {e}")
    raise ServiceUnavailableError(f"Failed to fetch data: {e}")
except asyncio.TimeoutError:
    logger.error("Request timeout")
    raise TimeoutError("Data fetch timeout")

# Logging с контекстом
logger.error(
    "Failed to process file",
    extra={
        "file_id": file_id,
        "user_id": user_id,
        "error": str(e)
    }
)
```

### Logging
- **Production**: JSON формат ОБЯЗАТЕЛЕН (`LOG_FORMAT=json`)
- **Development**: Text формат разрешен (`LOG_FORMAT=text`)
- Structured logging с контекстными полями

```python
import structlog

logger = structlog.get_logger(__name__)

logger.info(
    "File uploaded successfully",
    file_id=file_id,
    user_id=user_id,
    size_bytes=file_size,
    storage_element=storage_id
)
```

## FastAPI Code Style

### API Endpoints
```python
from fastapi import APIRouter, Depends, HTTPException, status
from typing import List

router = APIRouter(prefix="/api/v1/files", tags=["files"])

@router.get(
    "/{file_id}",
    response_model=FileResponse,
    summary="Получить информацию о файле",
    description="Возвращает метаданные файла по его ID"
)
async def get_file(
    file_id: str,
    current_user: User = Depends(get_current_user)
) -> FileResponse:
    """Получить информацию о файле."""
    if not file_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File ID is required"
        )
    
    file = await file_service.get_by_id(file_id)
    if not file:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"File {file_id} not found"
        )
    
    return FileResponse.from_orm(file)
```

### Pydantic Models
```python
from pydantic import BaseModel, Field, ConfigDict
from typing import Optional
from datetime import datetime

class FileBase(BaseModel):
    """Базовая схема файла."""
    filename: str = Field(..., min_length=1, max_length=255)
    content_type: str
    size_bytes: int = Field(..., gt=0)

class FileCreate(FileBase):
    """Схема для создания файла."""
    storage_element_id: str

class FileResponse(FileBase):
    """Схема ответа с информацией о файле."""
    id: str
    checksum: str
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    model_config = ConfigDict(from_attributes=True)
```

## SQLAlchemy Models

```python
from sqlalchemy import Column, String, Integer, DateTime, Boolean
from sqlalchemy.sql import func
from app.models.base import Base

class ServiceAccount(Base):
    """Модель Service Account."""
    __tablename__ = "service_accounts"
    
    id = Column(String(36), primary_key=True)
    name = Column(String(255), unique=True, nullable=False, index=True)
    client_id = Column(String(255), unique=True, nullable=False, index=True)
    client_secret_hash = Column(String(255), nullable=False)
    role = Column(String(50), nullable=False, default="USER")
    is_active = Column(Boolean, default=True, nullable=False)
    is_system = Column(Boolean, default=False, nullable=False)
    
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )
    updated_at = Column(
        DateTime(timezone=True),
        onupdate=func.now()
    )
    
    def __repr__(self) -> str:
        return f"<ServiceAccount(id={self.id}, name={self.name})>"
```

## Testing Style

### Pytest конфигурация
```ini
[pytest]
minversion = 7.0
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*
asyncio_mode = auto

addopts =
    -v
    --strict-markers
    --tb=short
    --disable-warnings

markers =
    unit: Unit tests
    integration: Integration tests
    slow: Slow tests
    asyncio: Async tests
```

### Test Structure
```python
import pytest
from unittest.mock import AsyncMock, patch

class TestServiceAccountService:
    """Тесты для ServiceAccountService."""
    
    @pytest.fixture
    def service(self, db_session):
        """Fixture для service."""
        return ServiceAccountService(db_session)
    
    @pytest.mark.asyncio
    async def test_create_service_account_success(self, service):
        """Тест успешного создания service account."""
        # Arrange
        data = ServiceAccountCreate(
            name="test-account",
            role="USER"
        )
        
        # Act
        result = await service.create(data)
        
        # Assert
        assert result.name == "test-account"
        assert result.role == "USER"
        assert result.is_active is True
    
    @pytest.mark.asyncio
    async def test_create_duplicate_name_fails(self, service):
        """Тест создания account с дублирующимся именем."""
        # Arrange
        data = ServiceAccountCreate(name="existing", role="USER")
        await service.create(data)
        
        # Act & Assert
        with pytest.raises(DuplicateNameError):
            await service.create(data)
```

## Docker Best Practices

### Dockerfile Structure
```dockerfile
# Multi-stage build
FROM python:3.12-slim as builder

# Builder stage
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ make libpq-dev \
    && rm -rf /var/lib/apt/lists/*

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Runtime stage
FROM python:3.12-slim

COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /app
COPY . .

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### docker-compose.yml
```yaml
services:
  admin-module:
    build:
      context: ./admin-module
      dockerfile: Dockerfile
    container_name: artstore_admin_module
    restart: unless-stopped
    environment:
      DB_HOST: postgres
      REDIS_HOST: redis
      LOG_FORMAT: ${LOG_FORMAT:-json}
    ports:
      - "8000:8000"
    networks:
      - artstore_network
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
```

## Git Commit Messages

Формат: `<type>: <subject>`

### Types:
- `feat`: Новая функциональность
- `fix`: Исправление бага
- `docs`: Изменения в документации
- `test`: Добавление/изменение тестов
- `refactor`: Рефакторинг кода
- `chore`: Обновление зависимостей, конфигурации
- `perf`: Улучшение производительности
- `style`: Форматирование кода

### Примеры:
```
feat: добавить endpoint для загрузки файлов
fix: исправить race condition в Service Discovery
docs: обновить README с инструкциями по deployment
test: добавить unit тесты для auth_service
refactor: переписать file upload на streaming
chore: обновить FastAPI до версии 0.115.5
```

## Configuration Management

### Environment Variables
```python
# app/core/config.py
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Literal

class Settings(BaseSettings):
    """Настройки приложения."""
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False
    )
    
    # Database
    db_host: str = "localhost"
    db_port: int = 5432
    db_username: str = "artstore"
    db_password: str
    db_name: str = "artstore"
    
    # Redis
    redis_host: str = "localhost"
    redis_port: int = 6379
    
    # Logging
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    log_format: Literal["text", "json"] = "json"
    
    @property
    def database_url(self) -> str:
        """Формирование database URL."""
        return (
            f"postgresql+asyncpg://{self.db_username}:"
            f"{self.db_password}@{self.db_host}:"
            f"{self.db_port}/{self.db_name}"
        )

settings = Settings()
```

## Security Best Practices

1. **Never commit secrets**: Используй `.env` файлы (в `.gitignore`)
2. **JWT RS256**: Только асимметричная криптография
3. **Password hashing**: Используй bcrypt с достаточной сложностью
4. **Rate limiting**: На все публичные endpoints
5. **Input validation**: Всегда через Pydantic
6. **SQL injection protection**: Используй ORM или параметризованные запросы
7. **CORS**: Настраивай явно, не используй `allow_origins=["*"]` в production