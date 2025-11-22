# Требования и ограничения проекта ArtStore

**Дата создания**: 2025-11-14
**Приоритет**: КРИТИЧЕСКИЙ

## Обязательные правила разработки

### 1. Обновление документации после каждого этапа
**Правило**: Всегда после завершения stage вносить изменения в DEVELOPMENT_PLAN.md

**Детали**:
- После каждого Sprint/Phase обновлять статус в плане разработки
- Актуализировать проценты завершенности модулей
- Обновлять списки завершенных/в процессе/запланированных задач
- Фиксировать фактические даты завершения этапов
- Документировать технические достижения и метрики

### 2. Исключения из scope разработки
**Правило**: НЕ предлагать и НЕ разрабатывать CI/CD Automation

**Обоснование**:
- CI/CD Automation не является задачей текущей разработки
- Фокус проекта на core functionality микросервисов
- Инфраструктура развертывания вне scope текущего проекта

**Запрещенные предложения**:
- ❌ GitHub Actions workflows
- ❌ Pre-commit hooks setup
- ❌ Automated testing pipelines
- ❌ Continuous deployment automation
- ❌ Jenkins/GitLab CI configuration

**Разрешенные инструменты для локальной разработки**:
- ✅ Docker и docker-compose для разработки
- ✅ Manual testing через pytest
- ✅ Manual code quality checks
- ✅ Manual deployment procedures

### 3. Фокус на core functionality
**Приоритеты проекта**:
1. Микросервисная архитектура (Admin, Storage Element, Ingester, Query)
2. OAuth 2.0 аутентификация (Service Accounts)
3. Template Schema v2.0 для метаданных
4. Integration tests для качества кода
5. Базовая функциональность модулей

**Вне приоритетов**:
- Автоматизация CI/CD процессов
- DevOps infrastructure as code
- Automated deployment pipelines
- Monitoring automation setup

## Текущий контекст разработки

### Завершенные Sprint'ы
- ✅ Sprint 1-3: Foundation + OAuth 2.0 (COMPLETE)
- ✅ Sprint 4-6: Template Schema v2.0 + JWT Tests (COMPLETE)
- ✅ Sprint 7: Integration Tests Real HTTP Migration (COMPLETE, 93.5%)
- ✅ Sprint 8: Pragmatic Testing Strategy (ANALYSIS COMPLETE)
- ✅ Sprint 9: Integration Tests 100% Success (COMPLETE)
- ✅ Sprint 10 Phase 1-2: Utils Coverage Enhancement (COMPLETE)

### Текущий статус (2025-11-14)
- **Admin Module**: 80% (OAuth ✅, LDAP pending removal)
- **Storage Element**: 70% (Router ✅, Docker ✅, Template Schema v2.0 ✅, Tests ✅)
- **Integration Tests**: 31/31 passing (100%)
- **Utils Coverage**: file_naming.py 100%, attr_utils.py 88%
- **Overall Coverage**: ~47-50%

### Следующие приоритеты
1. **Ingester Module Development** - File upload orchestration
2. **Query Module Development** - PostgreSQL FTS, file search
3. **Service Discovery Implementation** - Redis Pub/Sub coordination
4. **LDAP Infrastructure Removal** - Clean up после OAuth migration

## Исторический контекст

### Архитектурные изменения (2025-01-12)
**Источник**: `.archive/sq.md`

**Ключевое требование заказчика**:
> "Система не предназначена для непосредственного использования конечными пользователей.
> Системой будут пользоваться другие приложения.
> Следовательно, пользователи будут только локальные и не надо реализовывать хранение их
> учетных записей в LDAP."

**Реализованные изменения**:
- ✅ OAuth 2.0 Client Credentials вместо LDAP authentication
- ✅ Service Accounts для machine-to-machine auth
- ⏳ LDAP infrastructure removal (planned Sprint 11-12)

## Compliance Checklist

При работе над проектом:
- [ ] После завершения Sprint обновить DEVELOPMENT_PLAN.md
- [ ] Обновить статус модулей (проценты завершенности)
- [ ] Зафиксировать метрики (тесты, покрытие)
- [ ] Документировать технические достижения
- [ ] НЕ предлагать CI/CD automation
- [ ] Фокусироваться на core functionality
