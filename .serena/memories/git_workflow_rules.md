# Git Workflow для работы над задачами

## ОБЯЗАТЕЛЬНОЕ ПРАВИЛО

При выполнении любых задач, связанных с изменением файлов проекта, ВСЕГДА следовать этому workflow:

## Workflow

### 1. Перед началом работы

```bash
# Убедиться что на main и актуален
git checkout main
git pull origin main

# Создать feature branch
git checkout -b <type>/<short-description>
```

**Branch naming (из DEVELOPMENT-GUIDE.md):**
- `feature/` - Новые features
- `bugfix/` - Исправления bugs
- `docs/` - Документация
- `refactor/` - Рефакторинг без изменения функционала
- `test/` - Добавление/улучшение тестов
- `hotfix/` - Критические production fixes

**Примеры:**
- `feature/admin-auth-oauth2`
- `docs/auth-mechanics-documentation`
- `bugfix/storage-element-wal-race-condition`

### 2. Выполнение работы

- Делать изменения в созданной ветке
- Можно делать промежуточные commits при необходимости

### 3. По завершении задачи - предложить commit

**Спросить пользователя:**
> Работа завершена. Создать commit?

**Commit message format (Conventional Commits):**
```
<type>(<scope>): <subject>

[optional body]
```

**Types:**
- `feat`: Новая функциональность
- `fix`: Исправление бага
- `docs`: Документация
- `style`: Форматирование
- `refactor`: Рефакторинг
- `test`: Тесты
- `chore`: Maintenance

### 4. После commit - предложить merge на выбор

**Спросить пользователя:**
> Commit создан. Выберите способ merge:
> 
> **[A] Локальный merge в main:**
> ```bash
> git checkout main
> git merge --no-ff <branch-name>
> git push origin main
> ```
> 
> **[B] GitHub PR с автоматическим merge:**
> ```bash
> gh pr create --fill
> gh pr merge --auto --merge
> ```

### 5. После merge - удалить временную ветку

```bash
# Удалить локальную ветку
git branch -d <branch-name>

# Удалить remote ветку (если была)
git push origin --delete <branch-name>
```

## Важные правила

1. **НИКОГДА не работать напрямую в main** - всегда создавать feature branch
2. **Короткоживущие ветки** - merge как можно скорее (Trunk-Based Development)
3. **Conventional Commits** - всегда использовать правильный формат
4. **Удалять ветки после merge** - не оставлять мусор

## Исключения

- Если пользователь явно просит работать в main - уточнить причину
- Для экстренных hotfix можно работать быстрее, но всё равно через ветку

## Пример полного цикла

```bash
# 1. Создание ветки
git checkout main && git pull
git checkout -b docs/update-readme-authentication

# 2. Работа... (изменения файлов)

# 3. Commit
git add .
git commit -m "docs(admin-module): Add authentication documentation"

# 4. Merge (вариант A - локальный)
git checkout main
git merge --no-ff docs/update-readme-authentication
git push origin main

# 5. Cleanup
git branch -d docs/update-readme-authentication
```
