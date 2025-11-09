# ArtStore - Чеклист завершения задач

## При завершении любой задачи разработки

### 1. Код ревью (самопроверка)

- [ ] Код следует конвенциям проекта (см. `code_style_and_conventions.md`)
- [ ] Комментарии на русском языке
- [ ] Подробные docstrings для функций и классов
- [ ] Type hints для всех параметров и возвращаемых значений
- [ ] Нет hardcoded значений (используется конфигурация)
- [ ] Нет секретов в коде (пароли, ключи через environment variables)

### 2. Тестирование

```bash
# Запустить все тесты модуля
cd [module-name]
py -m pytest tests/ -v

# Проверить coverage (должен быть >80%)
py -m pytest tests/ --cov=app --cov-report=html

# Просмотреть отчет coverage
start htmlcov/index.html
```

**Требования к тестам**:
- [ ] Unit тесты для новой функциональности
- [ ] Integration тесты для API endpoints
- [ ] Coverage >= 80% для измененного кода
- [ ] Все тесты проходят успешно

### 3. Линтинг и форматирование (если настроено)

```bash
# Black форматирование
black app/

# Ruff линтер
ruff check app/

# MyPy type checking
mypy app/
```

### 4. Миграции базы данных (если применимо)

```bash
# Создать миграцию для изменений в моделях
alembic revision --autogenerate -m "Описание изменений"

# Применить миграцию
alembic upgrade head

# Проверить, что миграция применилась
alembic current
```

### 5. Документация

- [ ] Обновлен README.md модуля (если необходимо)
- [ ] Добавлены примеры использования API (если новые endpoints)
- [ ] Обновлена документация конфигурации (если новые параметры)
- [ ] Комментарии в коде объясняют "почему", а не "что"

### 6. Health checks и мониторинг

```bash
# Проверить health endpoints
curl http://localhost:8000/health/live
curl http://localhost:8000/health/ready

# Проверить metrics endpoint
curl http://localhost:8000/metrics
```

**Требования**:
- [ ] /health/live возвращает 200 OK
- [ ] /health/ready возвращает 200 OK при готовности к работе
- [ ] /metrics содержит метрики Prometheus
- [ ] Добавлены custom metrics для новой функциональности (если применимо)

### 7. Логирование

- [ ] Критические операции логируются с уровнем INFO
- [ ] Ошибки логируются с уровнем ERROR и stack trace
- [ ] Логи в JSON формате
- [ ] Присутствует trace_id для корреляции запросов
- [ ] Sensitive данные (пароли, токены) не логируются

### 8. Безопасность

- [ ] Все API endpoints требуют JWT аутентификацию (кроме health checks)
- [ ] Проверка прав доступа (RBAC) реализована
- [ ] SQL инъекции предотвращены (используется ORM или параметризованные запросы)
- [ ] XSS защита (валидация и санитизация входных данных)
- [ ] Secrets не в коде (через environment variables или secrets management)

### 9. Производительность

- [ ] Используется async/await для I/O операций
- [ ] Database queries оптимизированы (нет N+1, используются индексы)
- [ ] Connection pooling настроен для БД и Redis
- [ ] Большие файлы обрабатываются через streaming
- [ ] Кеширование реализовано для частых запросов

### 10. Интеграция

```bash
# Проверить работу с инфраструктурой
docker-compose ps  # Все сервисы должны быть "Up"

# Проверить подключение к PostgreSQL
docker exec -it artstore_postgres psql -U artstore -d artstore -c "SELECT 1"

# Проверить подключение к Redis
docker exec -it artstore_redis redis-cli ping
```

**Требования**:
- [ ] Подключение к PostgreSQL работает
- [ ] Подключение к Redis работает
- [ ] Подключение к MinIO/S3 работает (если используется)
- [ ] LDAP аутентификация работает (если используется)

### 11. Git коммит

```bash
# Проверить статус
git status

# Добавить изменения
git add .

# Коммит с описательным сообщением на русском
git commit -m "feat: добавлена функциональность загрузки файлов

- Реализован endpoint POST /api/v1/files/upload
- Добавлена валидация размера файла
- Настроено streaming upload
- Добавлены тесты для upload функциональности
- Coverage: 85%"

# Push в feature branch
git push origin feature/file-upload
```

**Формат commit message**:
- Тип: `feat`, `fix`, `refactor`, `docs`, `test`, `chore`
- Краткое описание (до 72 символов)
- Подробное описание изменений (опционально)
- Список изменений bullet points

### 12. Docker образ (если применимо)

```bash
# Собрать Docker образ
docker build -t artstore/[module-name]:latest ./[module-name]

# Проверить образ
docker images | grep artstore

# Запустить контейнер для проверки
docker run -p 8000:8000 artstore/[module-name]:latest

# Проверить health
curl http://localhost:8000/health/live
```

## Специфичные чеклисты для типов задач

### Новый API endpoint

- [ ] OpenAPI документация сгенерирована автоматически
- [ ] Pydantic схемы для request/response
- [ ] Обработка ошибок и валидация входных данных
- [ ] Rate limiting настроен (если необходимо)
- [ ] API версионирование (`/api/v1/`)
- [ ] Integration тесты с различными сценариями
- [ ] Документированы примеры curl запросов

### Изменение модели БД

- [ ] Alembic миграция создана
- [ ] Миграция протестирована (upgrade + downgrade)
- [ ] Индексы созданы для часто запрашиваемых полей
- [ ] Foreign keys настроены правильно
- [ ] ON DELETE / ON UPDATE behavior определен
- [ ] Seed data обновлен (если необходимо)

### Новая конфигурация

- [ ] Параметр добавлен в config.yaml с описанием
- [ ] Environment variable поддерживается
- [ ] Значение по умолчанию определено
- [ ] Валидация значения реализована
- [ ] Документация обновлена
- [ ] Пример в config.yaml.example

### Интеграция внешнего сервиса

- [ ] Circuit breaker реализован
- [ ] Retry логика с exponential backoff
- [ ] Timeout настроен
- [ ] Fallback механизм реализован
- [ ] Health check внешнего сервиса
- [ ] Метрики для мониторинга интеграции

## Финальная проверка перед merge

- [ ] Все тесты проходят локально
- [ ] Coverage >= 80%
- [ ] Линтеры не показывают ошибок
- [ ] Health checks работают
- [ ] Миграции применяются без ошибок
- [ ] Документация обновлена
- [ ] Коммит имеет описательное сообщение
- [ ] Feature branch обновлен с main/master
- [ ] Нет конфликтов при merge
