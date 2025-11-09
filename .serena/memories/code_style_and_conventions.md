# ArtStore - Стиль кода и конвенции

## Общие правила

- **Язык комментариев**: Все комментарии в коде на **русском языке**
- **Язык ответов**: Отвечать на русском языке
- **Платформа разработки**: Windows 11 (cmd.exe / PowerShell)
- **Честность**: Если не знаешь ответ - скажи "Не знаю ответ", не выдумывай
- **Зацикливание**: Если видишь, что задачи зациклились - остановись и спроси что делать

## Python код

### Версия и стиль
- Python >= 3.12
- PEP 8 compliance
- Type hints обязательны
- Async/await для всех I/O операций

### Naming conventions
- `snake_case` для функций, переменных, модулей
- `PascalCase` для классов
- `UPPER_CASE` для констант
- Префикс `_` для приватных методов

### Docstrings
```python
def example_function(param: str) -> dict:
    """
    Краткое описание функции на русском языке.
    
    Args:
        param: Описание параметра на русском
        
    Returns:
        Словарь с результатами
        
    Raises:
        ValueError: Когда param пустой
    """
    pass
```

### Imports
```python
# Стандартная библиотека
import os
from pathlib import Path

# Сторонние библиотеки
from fastapi import FastAPI
from sqlalchemy import select

# Локальные импорты
from app.core.config import settings
from app.models.user import User
```

## Структура проектов модулей

```
module-name/
├── app/
│   ├── __init__.py
│   ├── main.py           # FastAPI приложение
│   ├── core/             # Конфигурация, безопасность
│   │   ├── config.py
│   │   ├── security.py
│   │   └── logging.py
│   ├── api/              # REST API endpoints
│   │   ├── v1/
│   │   │   ├── endpoints/
│   │   │   └── router.py
│   │   └── deps.py       # Зависимости FastAPI
│   ├── models/           # SQLAlchemy модели
│   ├── schemas/          # Pydantic схемы
│   ├── services/         # Бизнес-логика
│   ├── db/               # База данных
│   │   ├── session.py
│   │   └── base.py
│   └── utils/            # Утилиты
├── tests/                # Тесты
│   ├── unit/
│   ├── integration/
│   └── conftest.py
├── alembic/              # Миграции БД
│   ├── versions/
│   └── env.py
├── config/               # Конфигурационные файлы
│   └── config.yaml
├── Dockerfile
├── requirements.txt
└── README.md
```

## Конфигурация

### YAML формат
```yaml
# Конфигурация на русском языке с английскими ключами
app:
  name: "module-name"
  version: "1.0.0"
  debug: true

database:
  host: "localhost"
  port: 5432
  username: "artstore"
  password: "password"
  database: "artstore"
```

### Environment variables
- Переменные окружения имеют приоритет над конфигурацией
- Формат: `MODULE_SECTION_KEY` (например: `ADMIN_DATABASE_HOST`)

## File naming convention

### Storage files
```
{name_without_ext}_{username}_{timestamp}_{uuid}.{ext}
```

Пример:
```
report_ivanov_20250102T153045_a1b2c3d4.pdf
```

### Attribute files
```
{storage_filename}.attr.json
```

Пример:
```
report_ivanov_20250102T153045_a1b2c3d4.pdf.attr.json
```

## Логирование

### Формат
- Структурированное логирование (JSON по умолчанию)
- Уровни: DEBUG, INFO, WARNING, ERROR, CRITICAL
- Обязательные поля: timestamp, level, message, module, trace_id

### Пример
```python
import logging

logger = logging.getLogger(__name__)

logger.info(
    "Файл загружен",
    extra={
        "file_id": file_id,
        "username": username,
        "size_bytes": size
    }
)
```

## API Conventions

### REST Endpoints
- Версионирование: `/api/v1/`
- Resource naming: множественное число (`/users`, `/files`)
- HTTP методы по назначению (GET, POST, PUT, DELETE)

### Response format
```json
{
  "status": "success",
  "data": { ... },
  "metadata": {
    "timestamp": "2025-01-09T12:00:00Z",
    "trace_id": "uuid"
  }
}
```

### Error response
```json
{
  "status": "error",
  "error": {
    "code": "FILE_NOT_FOUND",
    "message": "Файл не найден",
    "details": { ... }
  },
  "metadata": {
    "timestamp": "2025-01-09T12:00:00Z",
    "trace_id": "uuid"
  }
}
```

## Database conventions

### Table naming
- Префикс для уникальности: `{table_prefix}_tablename`
- Пример: `storage_elem_01_files`

### Column naming
- `snake_case`
- Timestamps: `created_at`, `updated_at`
- Foreign keys: `{table}_id`

## Git conventions

### Branch naming
- `feature/feature-name`
- `bugfix/bug-description`
- `hotfix/critical-fix`

### Commit messages
- На русском языке
- Формат: `тип: краткое описание`
- Типы: feat, fix, refactor, docs, test, chore
