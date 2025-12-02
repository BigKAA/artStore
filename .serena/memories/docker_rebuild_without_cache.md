# Docker Rebuild Without Cache - Critical Information

## ВАЖНО: При изменениях Python кода

При изменении Python файлов в модулях системы (admin-module, ingester-module, query-module, storage-element) **ОБЯЗАТЕЛЬНО** пересобирать контейнеры без кеша:

```bash
# ПРАВИЛЬНО - пересборка без кеша:
docker-compose build --no-cache [module-name]
docker-compose up -d [module-name]

# НЕПРАВИЛЬНО - обычная пересборка (может использовать устаревший код):
docker-compose build [module-name]
```

## Причина

Docker кеширует слои образа. Если изменения только в Python файлах (COPY ./app /app/app), Docker может использовать кешированный слой и не скопировать обновлённый код.

## Примеры команд

```bash
# Пересборка конкретного модуля
docker-compose build --no-cache admin-module
docker-compose build --no-cache ingester-module
docker-compose build --no-cache query-module
docker-compose build --no-cache storage-element

# Запуск после пересборки
docker-compose up -d [module-name]

# Пересборка и запуск в одну команду
docker-compose up -d --build --force-recreate [module-name]
```

## Когда использовать --no-cache

1. При изменении Python кода в `/app` директории
2. При обновлении конфигурации приложения
3. При добавлении новых файлов
4. При исправлении ошибок импорта
5. Если после `docker-compose build` изменения не применились

## Дополнительные команды для отладки

```bash
# Просмотр логов модуля
docker-compose logs -f [module-name]

# Проверка что контейнер работает
docker-compose ps

# Остановка и удаление контейнера перед пересборкой
docker-compose down [module-name]
docker-compose build --no-cache [module-name]
docker-compose up -d [module-name]
```

## Дата добавления
2025-12-02 (Sprint 15)
