# План реализации: Удаление STORAGE_ELEMENT_BASE_URL и стандартизация health checks

## Обзор изменений

Этот план детализирует два критических архитектурных улучшения для ArtStore Ingester Module:

1. **Полное удаление устаревшей конфигурации `STORAGE_ELEMENT_BASE_URL`**
2. **Стандартизация health check endpoints для соответствия архитектуре системы**
3. **Реализация проверки ВСЕХ writable Storage Elements в health checks**

## Текущее состояние

### Проблема 1: Статическая конфигурация как fallback

**Затронутые файлы (9 мест):**
- `ingester-module/app/core/config.py:113` - определение `base_url` в `StorageElementSettings`
- `ingester-module/app/services/storage_selector.py:448` - fallback в `_select_from_local_config()`
- `ingester-module/app/services/upload_service.py:110,123,378,380` - fallback логика
- `ingester-module/app/services/finalize_service.py:345` - fallback в `_select_storage_element()`
- `ingester-module/app/api/v1/endpoints/health.py:82` - проверка единственного SE
- `ingester-module/app/api/v1/endpoints/finalize.py:140` - TODO с base_url
- `ingester-module/app/main.py:72` - логирование при старте
- `ingester-module/.env.example:26` - пример конфигурации
- `docker-compose.yml:532` - environment variable

**Текущая иерархия выбора SE:**
1. Redis Service Discovery (РАБОТАЕТ, Sprint 14)
2. Admin Module HTTP API fallback (РАБОТАЕТ)
3. **Local Config fallback (DEPRECATED, НАДО УДАЛИТЬ)**

### Проблема 2: Несоответствие health check endpoints

**Текущая ситуация:**

| Модуль | Liveness Path | Readiness Path |
|--------|---------------|----------------|
| Admin Module | `/health/live` | `/health/ready` |
| Storage Element | `/health/live` | `/health/ready` |
| **Ingester Module** | **`/api/v1/health/live`** | **`/api/v1/health/ready`** |
| Query Module | `/health/live` | `/health/ready` |

**Несоответствие:**
- Ingester health check проверяет SE на НЕПРАВИЛЬНОМ endpoint: `/api/v1/health/live`
- Должен использовать: `/health/live`

### Проблема 3: Health check проверяет только один статический SE

**Текущая логика:**
- Проверяет только `settings.storage_element.base_url`
- НЕ проверяет другие SE из Service Discovery
- НЕ использует StorageSelector

**Требуемая логика:**
- Получить ВСЕ writable SE (режимы `edit`/`rw`)
- Проверить каждый на `/health/live`
- Агрегировать результаты (2/3 healthy = warning, 0/3 = fail)

---

## ФАЗА 1: Подготовка и анализ зависимостей

### 1.1 Проверка использования StorageSelector

**Файлы для проверки:**
- `ingester-module/app/services/upload_service.py` - метод `_select_storage_element()`
- `ingester-module/app/services/finalize_service.py` - метод `_select_storage_element()`
- `ingester-module/app/services/storage_selector.py` - методы `_select_from_redis()`, `_select_from_admin_module()`

**Проверить:**
- [ ] StorageSelector инициализируется в `main.py`
- [ ] `select_storage_element()` используется в сервисах
- [ ] Fallback на Admin Module API работает
- [ ] Логирование fallback операций присутствует

---

## ФАЗА 2: Удаление STORAGE_ELEMENT_BASE_URL

### 2.1 storage_selector.py

**Файл:** `ingester-module/app/services/storage_selector.py`

**Изменение 1 - Удалить метод (строки 440-478):**
```python
# УДАЛИТЬ ПОЛНОСТЬЮ:
# async def _select_from_local_config(...) -> Optional[StorageElementInfo]:
```

**Изменение 2 - Удалить вызов (строки 223-238):**
```python
# УДАЛИТЬ блок:
# # Попытка 3: Local config fallback
# se = await self._select_from_local_config(file_size, required_mode)
```

**Результат:** Только Redis → Admin Module API (без local fallback)

### 2.2 upload_service.py

**Файл:** `ingester-module/app/services/upload_service.py`

**Изменение 1 - `_select_storage_element()` (строки 374-380):**
```python
if not self._storage_selector:
    logger.error("StorageSelector not configured")
    raise RuntimeError(
        "StorageSelector is required. "
        "Ensure Redis or Admin Module API are available."
    )
```

**Изменение 2 - `_get_client()` (строки 107-127):**
```python
async def _get_client(self) -> httpx.AsyncClient:
    """DEPRECATED: Use _get_client_for_endpoint() instead."""
    raise NotImplementedError(
        "Direct client creation is deprecated. "
        "Use _get_client_for_endpoint() with SE from StorageSelector."
    )
```

### 2.3 finalize_service.py

**Файл:** `ingester-module/app/services/finalize_service.py`

**Изменение - `_select_storage_element()` (строки 342-345):**
```python
if not self._storage_selector:
    logger.error("StorageSelector not configured")
    raise RuntimeError(
        "StorageSelector required for finalization"
    )
```

### 2.4 finalize.py endpoint

**Файл:** `ingester-module/app/api/v1/endpoints/finalize.py`

**Изменение (строки 136-140):**
```python
# Получаем source SE через StorageSelector
logger.warning("Using first available SE (MVP)", extra={"file_id": file_id})

from app.services.storage_selector import RetentionPolicy as SelectorRetentionPolicy
source_se_info = await finalize_svc._storage_selector.select_storage_element(
    file_size=0,
    retention_policy=SelectorRetentionPolicy.PERMANENT
)

if not source_se_info:
    raise HTTPException(status_code=503, detail="No available SE")

source_se_id = source_se_info.element_id
source_se_endpoint = source_se_info.endpoint
```

### 2.5 health.py - КРИТИЧЕСКАЯ ПЕРЕРАБОТКА

**Файл:** `ingester-module/app/api/v1/endpoints/health.py`

**Полностью переписать `readiness_check()` (строки 75-96):**

Новая логика:
1. Проверить Redis (Service Discovery)
2. Проверить Admin Module (fallback)
3. Получить ВСЕ writable SE через StorageSelector
4. Проверить каждый SE на `/health/live` (БЕЗ `/api/v1`)
5. Агрегировать: ok (100%), degraded (>0% <100%), fail (0%)

```python
@router.get("/ready")
async def readiness_check():
    checks = {}
    overall_status = 'ok'
    
    # 1. Redis check
    try:
        redis_client = await get_redis_client()
        await redis_client.ping()
        checks['redis'] = 'ok'
    except Exception:
        checks['redis'] = 'fail'
        overall_status = 'degraded'
    
    # 2. Admin Module check
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{settings.auth.admin_module_url}/health/live")
            checks['admin_module'] = 'ok' if response.status_code == 200 else 'fail'
    except Exception:
        checks['admin_module'] = 'fail'
        overall_status = 'degraded'
    
    # 3. Storage Elements check
    storage_elements_status = {}
    healthy_se_count = 0
    total_se_count = 0
    
    try:
        redis_client = await get_redis_client() if checks.get('redis') == 'ok' else None
        selector = StorageSelector(redis_client=redis_client)
        
        # Получить edit и rw SE
        from app.services.storage_selector import RetentionPolicy
        edit_se = await selector.select_storage_element(file_size=0, retention_policy=RetentionPolicy.TEMPORARY)
        rw_se = await selector.select_storage_element(file_size=0, retention_policy=RetentionPolicy.PERMANENT)
        
        all_se = []
        if edit_se:
            all_se.append(edit_se)
        if rw_se and (not edit_se or rw_se.element_id != edit_se.element_id):
            all_se.append(rw_se)
        
        if not all_se:
            checks['storage_elements'] = 'fail'
            overall_status = 'fail'
        else:
            async with httpx.AsyncClient(timeout=5.0) as client:
                for se_info in all_se:
                    total_se_count += 1
                    try:
                        # ВАЖНО: /health/live БЕЗ /api/v1
                        response = await client.get(f"{se_info.endpoint}/health/live")
                        if response.status_code == 200:
                            storage_elements_status[se_info.element_id] = {'status': 'ok'}
                            healthy_se_count += 1
                        else:
                            storage_elements_status[se_info.element_id] = {'status': 'fail'}
                    except Exception:
                        storage_elements_status[se_info.element_id] = {'status': 'fail'}
            
            # Агрегация
            if healthy_se_count == 0:
                checks['storage_elements'] = 'fail'
                overall_status = 'fail'
            elif healthy_se_count < total_se_count:
                checks['storage_elements'] = 'degraded'
                if overall_status != 'fail':
                    overall_status = 'degraded'
            else:
                checks['storage_elements'] = 'ok'
    except Exception:
        checks['storage_elements'] = 'fail'
        overall_status = 'fail'
    
    response_data = {
        'status': overall_status,
        'checks': checks,
        'storage_elements': storage_elements_status,
        'summary': {
            'total_se': total_se_count,
            'healthy_se': healthy_se_count,
            'health_percentage': (healthy_se_count / total_se_count * 100) if total_se_count > 0 else 0
        }
    }
    
    status_code = 200 if overall_status == 'ok' else 503
    return JSONResponse(status_code=status_code, content=response_data)
```

### 2.6 main.py

**Файл:** `ingester-module/app/main.py`

**Изменение (строки 70-73):**
```python
logger.info(
    "Starting Ingester Module",
    extra={
        "service_discovery": "redis+admin_module",
        "redis_url": settings.redis.url,
        "admin_module_url": settings.auth.admin_module_url
    }
)
```

### 2.7 config.py

**Файл:** `ingester-module/app/core/config.py`

**Изменение (строки 105-117):**

Заменить `StorageElementSettings` на:
```python
class StorageElementClientSettings(BaseSettings):
    """HTTP client settings for SE communication.
    
    Endpoints получаются через Service Discovery.
    """
    
    model_config = SettingsConfigDict(
        env_prefix="STORAGE_ELEMENT_",
        case_sensitive=False
    )
    
    # НЕТ base_url!
    timeout: int = Field(default=30, description="Request timeout (seconds)")
    max_retries: int = Field(default=3, description="Max retry attempts")
    connection_pool_size: int = Field(default=100, description="Connection pool size")
```

В `Settings` классе:
```python
storage_element: StorageElementClientSettings = Field(
    default_factory=StorageElementClientSettings,
    description="HTTP client settings for SE"
)
```

### 2.8 .env.example

**Файл:** `ingester-module/.env.example`

**Изменение (строка 26):**
```bash
# Storage Element endpoints через Service Discovery (Redis/Admin Module)
STORAGE_ELEMENT_TIMEOUT=30
STORAGE_ELEMENT_MAX_RETRIES=3
STORAGE_ELEMENT_CONNECTION_POOL_SIZE=100
```

### 2.9 docker-compose.yml

**Файл:** `docker-compose.yml`

**Изменение (строка 532):**

Удалить:
```yaml
# STORAGE_ELEMENT_BASE_URL: http://storage-element-01:8000
```

Оставить:
```yaml
# Service Discovery
SERVICE_DISCOVERY_ENABLED: "on"
SERVICE_DISCOVERY_CHANNEL: artstore:storage-elements

# HTTP client
STORAGE_ELEMENT_TIMEOUT: 30
STORAGE_ELEMENT_MAX_RETRIES: 3
STORAGE_ELEMENT_CONNECTION_POOL_SIZE: 100
```

---

## ФАЗА 3: Стандартизация health check endpoints

### 3.1 router.py

**Файл:** `ingester-module/app/api/v1/router.py`

**Изменение (строки 17-20):**

Удалить health router:
```python
# УДАЛИТЬ:
# api_router.include_router(
#     health.router,
#     prefix="/health",
#     tags=["health"]
# )
```

### 3.2 main.py

**Файл:** `ingester-module/app/main.py`

**Добавить ПЕРЕД api_router:**
```python
# Health endpoints (БЕЗ /api/v1 prefix)
from app.api.v1.endpoints import health
app.include_router(health.router, prefix="/health", tags=["health"])
logger.info("Health endpoints: /health/live and /health/ready")

# API v1 router
app.include_router(api_router, prefix="/api/v1")
```

### 3.3 docker-compose.yml healthcheck

**Файл:** `docker-compose.yml`

**Изменение (строка 555):**
```yaml
healthcheck:
  test: ["CMD", "curl", "-f", "http://localhost:8020/health/live"]
  interval: 30s
  timeout: 10s
  retries: 3
  start_period: 60s
```

---

## ФАЗА 4: Обновление тестов

### 4.1 Unit тесты

**Файл:** `tests/unit/test_upload_service.py`

Добавить mock StorageSelector:
```python
@pytest.fixture
def mock_storage_selector():
    selector = Mock(spec=StorageSelector)
    
    async def mock_select(file_size, retention_policy):
        from app.services.storage_selector import StorageElementInfo, CapacityStatus
        return StorageElementInfo(
            element_id="test-se-01",
            mode="rw",
            endpoint="http://test-storage:8010",
            priority=100,
            capacity_total=1000000000,
            capacity_used=100000000,
            capacity_free=900000000,
            capacity_percent=10.0,
            capacity_status=CapacityStatus.OK,
            health_status="healthy",
            last_updated=datetime.now(timezone.utc)
        )
    
    selector.select_storage_element = AsyncMock(side_effect=mock_select)
    return selector
```

### 4.2 Integration тесты

**Файл:** `tests/integration/test_health.py` (создать)

```python
@pytest.mark.asyncio
async def test_health_live_new_path(client):
    response = await client.get("/health/live")
    assert response.status_code == 200

@pytest.mark.asyncio
async def test_health_ready_checks_se(client):
    response = await client.get("/health/ready")
    assert response.status_code in [200, 503]
    data = response.json()
    assert "storage_elements" in data

@pytest.mark.asyncio
async def test_old_health_path_404(client):
    response = await client.get("/api/v1/health/live")
    assert response.status_code == 404
```

### 4.3 SE communication тесты

**Файл:** `tests/integration/test_storage_communication.py`

Изменить:
```python
# БЫЛО: f"{se_endpoint}/api/v1/health/live"
# СТАЛО: f"{se_endpoint}/health/live"
```

---

## ФАЗА 5: Документация

### 5.1 ingester-module/README.md

Добавить секции:
- Environment Variables (без base_url)
- Architecture Changes (Sprint 16)
- Health Checks стандарт

### 5.2 CLAUDE.md

Обновить:
- Service Discovery fallback иерархия
- Health Check стандарт

### 5.3 README.md

Обновить Service Discovery Protocol

---

## ФАЗА 6: Тестирование

### 6.1 Unit тесты

```bash
cd /home/artur/Projects/artStore/ingester-module
source ../.venv/bin/activate
pytest tests/unit/ -v --cov=app
```

Критерии:
- [ ] Все тесты проходят
- [ ] Coverage >80%

### 6.2 Integration тесты

```bash
pytest tests/integration/ -v
```

Критерии:
- [ ] Health на правильных путях
- [ ] SE check использует `/health/live`

### 6.3 Docker Compose

**Сценарий 1: Нормальная работа**
```bash
cd /home/artur/Projects/artStore
docker-compose up -d
curl http://localhost:8020/health/live
curl http://localhost:8020/health/ready
```

**Сценарий 2: Redis недоступен**
```bash
docker-compose stop redis
curl http://localhost:8020/health/ready
# Ожидается: degraded
```

**Сценарий 3: Redis И Admin недоступны**
```bash
docker-compose stop redis admin-module
curl http://localhost:8020/health/ready
# Ожидается: HTTP 503, fail
```

---

## ФАЗА 7: Rollback Strategy

### 7.1 Git rollback

```bash
git reset --hard HEAD
# или
git revert <commit-hash>
```

### 7.2 Emergency fallback

**ТОЛЬКО для emergency:**

docker-compose.yml:
```yaml
STORAGE_ELEMENT_BASE_URL: http://storage-element-01:8000
```

upload_service.py:
```python
if not self._storage_selector:
    logger.critical("EMERGENCY FALLBACK")
    return os.getenv("STORAGE_ELEMENT_BASE_URL"), "emergency-fallback"
```

---

## Критические точки и риски

### Риск 1: Redis И Admin недоступны

**Проблема:** Ingester не может выбрать SE

**Mitigation:**
- Health check → fail → Kubernetes не направит трафик
- Мониторинг алертит

**Rollback:** Emergency fallback (Фаза 7.2)

### Риск 2: Breaking change

**Проблема:** Внешние системы используют `/api/v1/health/live`

**Mitigation:**
- Health endpoints не в публичном API
- Только для Kubernetes probes

**Rollback:** Вернуть регистрацию в api_router

### Риск 3: Тесты ломаются

**Mitigation:**
- Обновить тесты ДО изменений
- Запустить для проверки

**Rollback:** Git revert

### Риск 4: StorageSelector = None

**Mitigation:**
- Проверить инициализацию в main.py
- Unit тесты покрывают сценарий

**Rollback:** Вернуть fallback с WARNING

---

## Чеклист выполнения

### Предварительные
- [ ] Прочитать план
- [ ] Service Discovery работает (Sprint 14)
- [ ] `git checkout -b feature/remove-static-storage-config`
- [ ] Backup конфигурации

### Фаза 1: Подготовка
- [ ] Проверить StorageSelector
- [ ] Проверить Redis Service Discovery
- [ ] Проверить Admin Module API fallback

### Фаза 2: Удаление base_url
- [ ] storage_selector.py
- [ ] upload_service.py
- [ ] finalize_service.py
- [ ] finalize.py endpoint
- [ ] health.py
- [ ] main.py
- [ ] config.py
- [ ] .env.example
- [ ] docker-compose.yml

### Фаза 3: Health checks
- [ ] router.py
- [ ] main.py
- [ ] docker-compose.yml healthcheck

### Фаза 4: Тесты
- [ ] Unit тесты
- [ ] Integration тесты health
- [ ] Integration тесты SE

### Фаза 5: Документация
- [ ] ingester-module/README.md
- [ ] CLAUDE.md
- [ ] README.md

### Фаза 6: Тестирование
- [ ] Unit тесты
- [ ] Integration тесты
- [ ] Docker Compose сценарии

### Финализация
- [ ] Code review
- [ ] Pull Request
- [ ] Merge

---

## Оценка времени

| Фаза | Время | Сложность |
|------|-------|-----------|
| 1: Подготовка | 1-2 часа | Низкая |
| 2: Удаление base_url | 3-4 часа | Средняя |
| 3: Health checks | 1-2 часа | Низкая |
| 4: Тесты | 3-4 часа | Средняя |
| 5: Документация | 1-2 часа | Низкая |
| 6: Тестирование | 2-3 часа | Средняя |
| 7: Rollback prep | 30 мин | Низкая |

**Общее:** 11-17 часов разработки

**Рекомендация:** 2-3 рабочих дня

---

## Критические файлы для реализации

### 1. storage_selector.py
**Строки:** 223-238, 440-478
**Критичность:** ВЫСОКАЯ - центральная логика Service Discovery

### 2. health.py
**Строки:** 75-96
**Критичность:** ВЫСОКАЯ - Kubernetes health probes

### 3. upload_service.py
**Строки:** 107-127, 374-380
**Критичность:** ВЫСОКАЯ - основной путь загрузки

### 4. config.py
**Строки:** 105-117
**Критичность:** СРЕДНЯЯ - breaking change конфигурации

### 5. docker-compose.yml
**Строки:** 532, 555
**Критичность:** СРЕДНЯЯ - production deployment

---

## Заключение

План обеспечивает:

1. **Полное удаление deprecated static configuration**
2. **Архитектурная консистентность**
3. **Улучшенная надежность**
4. **Backward compatibility при rollback**
5. **Comprehensive testing**

План готов к реализации. Выполнять пофазно с проверкой после каждой фазы.
