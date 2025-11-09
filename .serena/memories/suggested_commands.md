# ArtStore - Рекомендуемые команды

## Инфраструктура (Docker Compose)

### Запуск базовой инфраструктуры
```bash
# Запустить все сервисы инфраструктуры
docker-compose up -d

# Проверить статус
docker-compose ps

# Остановить все
docker-compose down

# Логи конкретного сервиса
docker-compose logs -f postgres
docker-compose logs -f redis
docker-compose logs -f minio
```

### Работа с PostgreSQL

```bash
# Подключиться к PostgreSQL в контейнере
docker exec -it artstore_postgres psql -U artstore -d artstore

# Создать новую базу данных (из контейнера)
docker exec -it artstore_postgres createdb -U artstore new_database_name

# Удалить базу данных (из контейнера)
docker exec -it artstore_postgres dropdb -U artstore database_name

# Список баз данных
docker exec -it artstore_postgres psql -U artstore -c "\l"
```

### Работа с MinIO

- Web Console: http://localhost:9001
- Credentials: minioadmin / minioadmin
- S3 API Endpoint: http://localhost:9000

### Работа с LDAP

```bash
# Подключение к LDAP
# Host: localhost:1389
# Bind DN: cn=Directory Manager
# Password: password
# Base DN: dc=artstore,dc=local
```

## Разработка модулей Python

### Создание виртуального окружения (внутри модуля)

```bash
cd admin-module
py -m venv venv

# Активация (Windows cmd)
venv\Scripts\activate.bat

# Активация (PowerShell)
venv\Scripts\Activate.ps1
```

### Установка зависимостей

```bash
# Установить зависимости модуля
py -m pip install -r requirements.txt

# Обновить pip
py -m pip install --upgrade pip

# Заморозить зависимости
py -m pip freeze > requirements.txt
```

### Запуск приложений FastAPI

```bash
# Admin Module
cd admin-module
py -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# Storage Element
cd storage-element
py -m uvicorn app.main:app --host 0.0.0.0 --port 8010 --reload

# Ingester Module
cd ingester-module
py -m uvicorn app.main:app --host 0.0.0.0 --port 8020 --reload

# Query Module
cd query-module
py -m uvicorn app.main:app --host 0.0.0.0 --port 8030 --reload
```

## Тестирование

### Запуск тестов

```bash
# Все тесты модуля
cd [module-name]
py -m pytest tests/ -v

# Конкретный файл тестов
py -m pytest tests/test_auth.py -v

# Тесты с coverage
py -m pytest tests/ --cov=app --cov-report=html

# Просмотр coverage отчета
start htmlcov/index.html  # Windows
```

### Запуск тестов с фильтрацией

```bash
# Только unit тесты
py -m pytest tests/unit/ -v

# Только integration тесты
py -m pytest tests/integration/ -v

# Тесты по маркеру
py -m pytest -m "slow" -v
```

## База данных - миграции Alembic

### Создание миграции

```bash
cd [module-name]

# Автоматическая миграция
alembic revision --autogenerate -m "Описание изменений"

# Ручная миграция
alembic revision -m "Описание изменений"
```

### Применение миграций

```bash
# Применить все миграции
alembic upgrade head

# Откатить одну миграцию
alembic downgrade -1

# Откатить все
alembic downgrade base

# История миграций
alembic history

# Текущая версия
alembic current
```

## Линтинг и форматирование (если настроено)

### Black (форматирование)

```bash
# Проверить без изменений
black --check app/

# Применить форматирование
black app/
```

### Ruff (линтер)

```bash
# Проверить код
ruff check app/

# Исправить автоматически
ruff check --fix app/
```

### MyPy (type checking)

```bash
# Проверить типы
mypy app/
```

## Docker операции для модулей

### Сборка Docker образа модуля

```bash
# Admin Module
docker build -t artstore/admin-module:latest ./admin-module

# Storage Element
docker build -t artstore/storage-element:latest ./storage-element
```

### Запуск модуля в Docker

```bash
# Запуск с docker-compose (если есть docker-compose-app.yml)
docker-compose -f docker-compose-app.yml up --build -d

# Остановка
docker-compose -f docker-compose-app.yml down
```

## Проверка здоровья сервисов

### Health checks

```bash
# Admin Module
curl http://localhost:8000/health/live
curl http://localhost:8000/health/ready

# Storage Element
curl http://localhost:8010/health/live
curl http://localhost:8010/health/ready

# Ingester
curl http://localhost:8020/health/live
curl http://localhost:8020/health/ready

# Query
curl http://localhost:8030/health/live
curl http://localhost:8030/health/ready
```

### Prometheus metrics

```bash
# Метрики модулей
curl http://localhost:8000/metrics  # Admin
curl http://localhost:8010/metrics  # Storage Element
curl http://localhost:8020/metrics  # Ingester
curl http://localhost:8030/metrics  # Query
```

## Git операции

### Базовые команды

```bash
# Статус репозитория
git status

# Добавить все изменения
git add .

# Коммит
git commit -m "feat: описание изменений"

# Пуш в удаленный репозиторий
git push origin feature-branch

# Просмотр истории
git log --oneline -10
```

### Работа с ветками

```bash
# Создать новую ветку
git checkout -b feature/new-feature

# Переключиться на ветку
git checkout main

# Список веток
git branch -a

# Удалить локальную ветку
git branch -d feature/old-feature
```

## Утилиты системы (Linux commands для WSL/Docker)

### Поиск файлов

```bash
# Найти Python файлы
find . -name "*.py"

# Найти по содержимому
grep -r "search_term" app/
```

### Просмотр файлов

```bash
# Просмотр файла
cat config/config.yaml

# Просмотр с нумерацией строк
cat -n app/main.py

# Последние строки логов
tail -f logs/app.log
```

### Управление процессами

```bash
# Найти процесс по порту
netstat -ano | findstr :8000

# В WSL/Docker
lsof -i :8000

# Убить процесс (Windows)
taskkill /PID <pid> /F
```

## Отладка

### Запуск с отладчиком

```bash
# Запуск с debugpy (если настроено)
py -m debugpy --listen 5678 --wait-for-client -m uvicorn app.main:app --reload
```

### Логи приложения

```bash
# Просмотр логов в реальном времени
tail -f logs/storage-element.log

# Поиск ошибок в логах
grep -i "error" logs/storage-element.log
```

## Очистка и maintenance

### Очистка Python кеша

```bash
# Удалить все __pycache__
find . -type d -name "__pycache__" -exec rm -r {} +

# Удалить .pyc файлы
find . -name "*.pyc" -delete
```

### Очистка Docker

```bash
# Удалить неиспользуемые образы
docker image prune -a

# Удалить неиспользуемые volumes
docker volume prune

# Полная очистка системы
docker system prune -a --volumes
```

## Полезные комбинации

### Полный перезапуск среды разработки

```bash
# Остановить все
docker-compose down

# Очистить volumes (ОСТОРОЖНО - удалит данные)
docker-compose down -v

# Запустить заново
docker-compose up -d

# Проверить здоровье
docker-compose ps
curl http://localhost:5432  # PostgreSQL
curl http://localhost:6379  # Redis
```

### Быстрая разработка модуля

```bash
# 1. Запустить инфраструктуру
docker-compose up -d

# 2. Перейти в модуль
cd storage-element

# 3. Установить зависимости (если не установлены)
py -m pip install -r requirements.txt

# 4. Запустить с hot reload
py -m uvicorn app.main:app --reload --port 8010

# 5. В другом терминале - запустить тесты в watch mode (если настроено)
py -m pytest tests/ -v --looponfail
```
