# Примеры использования JSON логирования

## Базовое логирование

```python
from app.core.logging_config import get_logger

logger = get_logger(__name__)

# Простое сообщение
logger.info("User logged in successfully")

# С форматированием
user_id = 123
logger.info(f"User {user_id} logged in successfully")
```

## Логирование с дополнительными полями (OpenTelemetry, трейсинг)

```python
from app.core.logging_config import get_logger

logger = get_logger(__name__)

# Добавление request_id, user_id, trace_id
logger.info(
    "User authentication successful",
    extra={
        'request_id': 'abc-123-def-456',
        'user_id': 123,
        'trace_id': 'trace-xyz-789',
        'span_id': 'span-001'
    }
)
```

## Вывод в JSON формате

```json
{
  "message": "User authentication successful",
  "request_id": "abc-123-def-456",
  "user_id": 123,
  "trace_id": "trace-xyz-789",
  "span_id": "span-001",
  "timestamp": "2025-11-09T19:30:00.123456+00:00",
  "level": "INFO",
  "logger": "app.api.v1.endpoints.auth",
  "module": "auth",
  "function": "login",
  "line": 45
}
```

## Логирование ошибок

```python
from app.core.logging_config import get_logger

logger = get_logger(__name__)

try:
    # Some operation
    result = perform_operation()
except Exception as e:
    logger.error(
        f"Operation failed: {str(e)}",
        extra={
            'error_type': type(e).__name__,
            'user_id': user_id,
            'request_id': request_id
        },
        exc_info=True  # Добавляет stack trace
    )
```

## Настройка формата логов

### Production (JSON формат - обязательно)

```yaml
# docker-compose.yml
environment:
  LOG_LEVEL: "INFO"
  LOG_FORMAT: "json"  # ОБЯЗАТЕЛЬНО для production
```

### Development (текстовый формат разрешен)

```yaml
# docker-compose.dev.yml
environment:
  LOG_LEVEL: "DEBUG"
  LOG_FORMAT: "text"  # Разрешен ТОЛЬКО в dev режиме
  APP_DEBUG: "true"   # Обязательно для text формата
```

## Интеграция с ELK Stack / Splunk

JSON логи автоматически совместимы с системами анализа логов:

### Filebeat конфигурация

```yaml
filebeat.inputs:
- type: container
  paths:
    - '/var/lib/docker/containers/*/*.log'
  json.keys_under_root: true
  json.add_error_key: true

processors:
  - add_docker_metadata:
      host: "unix:///var/run/docker.sock"
  - decode_json_fields:
      fields: ["message"]
      target: ""
      overwrite_keys: true

output.elasticsearch:
  hosts: ["elasticsearch:9200"]
  index: "artstore-admin-%{+yyyy.MM.dd}"
```

### Logstash filter

```ruby
filter {
  json {
    source => "message"
  }

  date {
    match => [ "timestamp", "ISO8601" ]
    target => "@timestamp"
  }
}
```

## Kibana / Grafana запросы

```
# Поиск по уровню ошибок
level: "ERROR"

# Поиск по пользователю
user_id: 123

# Поиск по request_id для трейсинга
request_id: "abc-123-def-456"

# Комбинированный поиск
level: "ERROR" AND module: "auth" AND user_id: 123
```
