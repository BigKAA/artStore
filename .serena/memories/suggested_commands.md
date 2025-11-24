# Полезные команды для разработки ArtStore

## 🔴 КРИТИЧЕСКИ ВАЖНО

**ВСЕГДА запускать Docker Compose из корня проекта**: `/home/artur/Projects/artStore`

```bash
cd /home/artur/Projects/artStore
```

## Быстрый старт

### Запуск всей системы
```bash
# Запуск всех сервисов
docker-compose up -d

# Просмотр логов
docker-compose logs -f

# Остановка
docker-compose down
```

### Запуск отдельных сервисов
```bash
# Только инфраструктура
docker-compose up -d postgres redis minio pgadmin

# Конкретный модуль
docker-compose up -d admin-module
docker-compose up -d storage-element
docker-compose up -d ingester-module
docker-compose up -d query-module

# С пересборкой
docker-compose build storage-element
docker-compose up -d storage-element
```

### Просмотр логов
```bash
# Все сервисы
docker-compose logs -f

# Конкретный сервис
docker-compose logs -f admin-module
docker-compose logs -f storage-element

# Последние N строк
docker-compose logs --tail=100 storage-element
```

## Python Virtual Environment

### Создание и активация venv
```bash
# Создание единого venv для всех модулей (один раз)
python3 -m venv .venv

# Активация
source .venv/bin/activate

# Установка зависимостей всех модулей
pip install -r admin-module/requirements.txt
pip install -r storage-element/requirements.txt
pip install -r ingester-module/requirements.txt
pip install -r query-module/requirements.txt
```

## Тестирование

### Запуск тестов
```bash
# Активировать venv
source .venv/bin/activate

# Запуск тестов модуля
cd admin-module
pytest tests/ -v

# С coverage
pytest tests/ --cov=app --cov-report=html

# Только unit тесты
pytest tests/ -v -m unit

# Только integration тесты
pytest tests/ -v -m integration

# Параллельное выполнение
pytest tests/ -n auto
```

### Coverage отчет
```bash
# Генерация HTML отчета
pytest tests/ --cov=app --cov-report=html

# Просмотр в браузере
xdg-open htmlcov/index.html
```

## Database операции

### PostgreSQL
```bash
# Подключение к БД
docker exec -it artstore_postgres psql -U artstore -d artstore

# Создание новой БД
docker exec -it artstore_postgres createdb -U artstore [db_name]

# Список баз данных
docker exec -it artstore_postgres psql -U artstore -c "\l"

# Backup БД
docker exec -it artstore_postgres pg_dump -U artstore artstore > backup.sql

# Restore БД
cat backup.sql | docker exec -i artstore_postgres psql -U artstore artstore
```

### Alembic миграции
```bash
# Активировать venv
source .venv/bin/activate

cd admin-module

# Создать новую миграцию
alembic revision --autogenerate -m "Description"

# Применить миграции
alembic upgrade head

# Откатить последнюю миграцию
alembic downgrade -1

# Просмотр истории миграций
alembic history
```

### Redis
```bash
# Подключение к Redis
docker exec -it artstore_redis redis-cli

# Просмотр всех ключей
docker exec -it artstore_redis redis-cli KEYS "*"

# Очистка Redis
docker exec -it artstore_redis redis-cli FLUSHALL
```

## Мониторинг

### Запуск мониторинга
```bash
# Запуск Prometheus + Grafana + AlertManager
docker-compose -f docker-compose.monitoring.yml up -d

# Просмотр логов мониторинга
docker-compose -f docker-compose.monitoring.yml logs -f

# Остановка мониторинга
docker-compose -f docker-compose.monitoring.yml down
```

### Доступ к интерфейсам
- **Prometheus**: http://localhost:9090
- **Grafana**: http://localhost:3000 (admin / admin123)
- **AlertManager**: http://localhost:9093
- **PgAdmin**: http://localhost:5050 (admin@admin.com / password)
- **MinIO Console**: http://localhost:9001 (minioadmin / minioadmin)

## API тестирование

### OAuth 2.0 аутентификация
```bash
# Получение access token
curl -X POST http://localhost:8000/api/auth/token \
  -H "Content-Type: application/json" \
  -d '{"client_id": "admin-service", "client_secret": "your-secret"}'

# Использование token
curl -X GET http://localhost:8000/api/service-accounts \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### Health checks
```bash
# Admin Module
curl http://localhost:8000/health/live
curl http://localhost:8000/health/ready

# Storage Element
curl http://localhost:8010/health/live
curl http://localhost:8010/health/ready

# Ingester Module
curl http://localhost:8020/health/live

# Query Module
curl http://localhost:8030/health/live
```

## Git workflow

### Создание feature branch
```bash
# Создать feature branch
git checkout -b feature/your-feature-name

# Работа с изменениями
git add .
git commit -m "feat: описание изменения"

# Push в remote
git push -u origin feature/your-feature-name
```

### Commit message convention
- `feat:` - новая функциональность
- `fix:` - исправление бага
- `docs:` - изменения в документации
- `test:` - добавление/изменение тестов
- `refactor:` - рефакторинг кода
- `chore:` - обновление зависимостей, конфигурации

## Полезные системные команды

### Docker очистка
```bash
# Очистка неиспользуемых ресурсов
docker system prune -f

# Очистка всех контейнеров и образов
docker system prune -a -f

# Очистка volumes
docker volume prune -f
```

### Проверка статуса
```bash
# Статус Docker контейнеров
docker-compose ps

# Использование ресурсов
docker stats

# Disk usage
docker system df
```

## Быстрый доступ к документации

- **README.md** - Полное описание проекта и архитектуры
- **DEVELOPMENT-GUIDE.md** - Руководство по разработке
- **admin-module/README.md** - Документация Admin Module
- **storage-element/README.md** - Документация Storage Element
- **ingester-module/README.md** - Документация Ingester Module
- **query-module/README.md** - Документация Query Module
- **CLAUDE.md** - Инструкции для AI-ассистента