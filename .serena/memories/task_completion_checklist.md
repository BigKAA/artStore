# Checklist при завершении задачи

## Перед коммитом

### 1. Тестирование
```bash
# Активировать venv
source .venv/bin/activate

# Запустить unit тесты
cd <module-name>
pytest tests/ -v -m unit

# Запустить все тесты
pytest tests/ -v

# Проверить coverage (должно быть >80%)
pytest tests/ --cov=app --cov-report=term-missing
```

### 2. Линтинг и форматирование
```bash
# Проверка стиля кода (если настроено)
flake8 app/
pylint app/

# Проверка type hints (если настроено)
mypy app/
```

### 3. Проверка работоспособности

#### Запуск модуля локально
```bash
cd /home/artur/Projects/artStore

# Пересборка модуля
docker-compose build <module-name>

# Запуск
docker-compose up -d <module-name>

# Проверка логов на ошибки
docker-compose logs -f <module-name>
```

#### Health checks
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

### 4. Документация

- [ ] Обновлены docstrings для новых/измененных функций
- [ ] Обновлен README-PROJECT.md модуля (если нужно)
- [ ] Добавлены примеры использования для новых API endpoints
- [ ] Обновлена OpenAPI документация FastAPI (автоматически)

### 5. Миграции базы данных

Если были изменения в моделях SQLAlchemy:

```bash
source .venv/bin/activate
cd <module-name>

# Создать миграцию
alembic revision --autogenerate -m "Описание изменений"

# Проверить сгенерированную миграцию
cat alembic/versions/<new_migration>.py

# Применить миграцию локально
alembic upgrade head

# Убедиться что миграция работает в обе стороны
alembic downgrade -1
alembic upgrade head
```

### 6. Environment Variables

Если добавлены новые переменные окружения:

- [ ] Обновлен `.env.example` файл модуля
- [ ] Обновлен `docker-compose.yml` с новыми переменными
- [ ] Документированы в README-PROJECT.md модуля

### 7. Git Status Check

```bash
# Проверить статус репозитория
git status

# Проверить изменения
git diff

# Проверить текущую ветку (не должно быть main/master)
git branch
```

## Коммит изменений

### 1. Создание коммита
```bash
# Добавить изменения
git add <файлы>

# Коммит с правильным сообщением
git commit -m "тип: описание изменения"

# Примеры:
git commit -m "feat: добавить endpoint для загрузки файлов"
git commit -m "fix: исправить race condition в Service Discovery"
git commit -m "test: добавить unit тесты для auth_service"
```

### 2. Push в remote
```bash
# Push в feature branch
git push origin feature/your-feature-name

# Если первый push
git push -u origin feature/your-feature-name
```

## Pull Request

### 1. Создание PR

- [ ] Создан PR в GitHub/GitLab
- [ ] Заполнено описание PR:
  - Что изменено
  - Зачем изменено
  - Как протестировано
- [ ] Указаны связанные issues (если есть)
- [ ] Назначен reviewer

### 2. PR Description Template

```markdown
## Описание изменений
[Краткое описание что изменено и зачем]

## Тип изменений
- [ ] Новая функциональность (feat)
- [ ] Исправление бага (fix)
- [ ] Рефакторинг (refactor)
- [ ] Документация (docs)
- [ ] Тесты (test)

## Как протестировано
- [ ] Unit тесты пройдены
- [ ] Integration тесты пройдены (если есть)
- [ ] Проверено локально в Docker
- [ ] Health checks работают
- [ ] API endpoints протестированы вручную

## Checklist
- [ ] Код следует style guide проекта
- [ ] Docstrings добавлены/обновлены
- [ ] Тесты добавлены/обновлены
- [ ] Coverage >= 80%
- [ ] README-PROJECT.md обновлен (если нужно)
- [ ] Миграции созданы (если нужно)
- [ ] .env.example обновлен (если нужно)
```

## После Merge

### 1. Cleanup

```bash
# Переключиться на main
git checkout main

# Обновить main
git pull origin main

# Удалить локальную feature branch
git branch -d feature/your-feature-name

# Удалить remote feature branch (если PR был merged)
git push origin --delete feature/your-feature-name
```

### 2. Deployment Verification

После автоматического deployment проверить:

- [ ] Сервис успешно запустился
- [ ] Health checks работают
- [ ] Мониторинг показывает нормальные метрики
- [ ] Логи не содержат ошибок

```bash
# Проверка через Docker
docker-compose ps
docker-compose logs -f <module-name>

# Проверка health
curl http://<host>:<port>/health/live
curl http://<host>:<port>/health/ready

# Проверка метрик
curl http://<host>:<port>/metrics
```

## Rollback План

Если что-то пошло не так после deployment:

```bash
# 1. Откатить изменения в Git
git revert <commit-hash>
git push origin main

# 2. Откатить миграции БД (если были)
cd <module-name>
alembic downgrade -1

# 3. Перезапустить сервис
docker-compose restart <module-name>

# 4. Проверить health
curl http://localhost:<port>/health/live
```

## Критические проверки перед Production

- [ ] ⚠️ **Secrets**: Все credentials в environment variables, не в коде
- [ ] ⚠️ **Logging**: LOG_FORMAT=json для production
- [ ] ⚠️ **Security**: JWT RS256, TLS настроен, rate limiting работает
- [ ] ⚠️ **Monitoring**: Prometheus метрики доступны
- [ ] ⚠️ **Backups**: Database backup настроен
- [ ] ⚠️ **Documentation**: API документация обновлена