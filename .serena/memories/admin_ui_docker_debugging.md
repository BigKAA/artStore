# Admin UI Docker - Руководство по отладке

## Контейнеризация Admin UI

Admin UI теперь запускается в Docker контейнере вместо локального `npm start`.

### Созданные файлы
- `admin-ui/Dockerfile` - Multi-stage build (Node → Nginx)
- `admin-ui/nginx.conf` - Reverse proxy конфигурация
- `admin-ui/.dockerignore` - Исключения для сборки

### Порты
- **4200** - Admin UI (Nginx)
- Внутри контейнера слушает порт 80

### Nginx Proxy Routes
- `/api/` → `admin-module:8000/api/`
- `/ingester/` → `ingester-module:8020/`
- `/query/` → `query-module:8030/`

## Команды для отладки

### Основные операции
```bash
# Просмотр логов в реальном времени
docker-compose logs -f admin-ui

# Статус контейнера
docker-compose ps admin-ui

# Перезапуск после изменений
docker-compose build admin-ui && docker-compose up -d admin-ui

# Shell внутри контейнера
docker-compose exec admin-ui sh

# Проверка конфигурации Nginx
docker-compose exec admin-ui nginx -t
```

### Просмотр файлов в контейнере
```bash
# Статические файлы Angular
docker-compose exec admin-ui ls -la /usr/share/nginx/html/

# Конфигурация Nginx
docker-compose exec admin-ui cat /etc/nginx/conf.d/default.conf
```

### Проверка работоспособности
```bash
# HTTP статус
curl -s -o /dev/null -w "%{http_code}" http://localhost:4200

# Проверка API proxy
curl -s http://localhost:4200/api/v1/health/live
```

## Типичные проблемы

### 1. Порт 4200 занят
```bash
# Остановить npm start если запущен
pkill -f "ng serve"
# или
lsof -ti:4200 | xargs kill -9
```

### 2. Изменения не применяются
```bash
# Полная пересборка без кеша
docker-compose build --no-cache admin-ui
docker-compose up -d admin-ui
```

### 3. API proxy не работает
- Проверить что backend сервисы запущены
- Проверить имена сервисов в docker-compose (admin-module, ingester-module, query-module)
- Проверить логи Nginx: `docker-compose logs admin-ui`

### 4. Angular routing (404 на refresh)
- Nginx настроен с `try_files $uri $uri/ /index.html` для SPA routing
- Если 404 - проверить nginx.conf

## ВАЖНО: Отладка ведется в контейнере

После контейнеризации:
- НЕ использовать `npm start` для development
- Все изменения → пересборка контейнера
- Логи смотреть через `docker-compose logs`
- Файлы проверять через `docker-compose exec`
