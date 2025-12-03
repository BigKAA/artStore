# План тестирования Storage Element Selection Strategy (v2.0)

## 📋 Метаданные

**Проект**: ArtStore
**Версия плана**: 2.0 (улучшенная)
**Дата создания**: 2025-12-03
**Статус**: Ready for Execution
**Автор**: Claude Code (на основе 1stTEST.md)

## 🎯 Цель тестирования

Протестировать корректность реализации **Storage Element Selection Strategy** (Sequential Fill Algorithm) с проверкой:
- Последовательного заполнения Storage Elements по priority
- Переходов Capacity Status (OK → WARNING → CRITICAL → FULL)
- Автоматического переключения на следующий SE при заполнении
- Fallback механизмов (Redis → Admin API → Local Config)
- File Lifecycle Management (TEMPORARY → PERMANENT)

---

## 🔍 Анализ и улучшения от 1stTEST.md

### Выявленные проблемы
1. ❌ Недостаточная детализация API методов
2. ❌ Нечеткие критерии валидации (как измерять 96%?)
3. ❌ Отсутствие негативных сценариев (Redis down, Admin down)
4. ❌ Неясная процедура миграции файлов
5. ❌ WEB UI тестирование - вопрос без ответа
6. ❌ Отсутствие baseline метрик для сравнения
7. ❌ Нет rollback процедуры при провале

### Ключевые улучшения
✅ **Структура**: 6 фаз (Pre-Flight → Подготовка → Baseline → Позитивные → Негативные → Валидация)
✅ **Автоматизация**: 9 bash/python скриптов для полной автоматизации
✅ **Метрики**: Конкретные Prometheus метрики для каждого этапа
✅ **API детализация**: Полные endpoint спецификации с примерами curl
✅ **Негативные сценарии**: T8, T9, T10 для fallback механизмов
✅ **Критерии**: Четкие success/fail критерии для каждого теста
✅ **WEB UI ответ**: Отдельный тест после Backend (обосновано)

---

## 🏗️ Тестовая конфигурация

**Storage Elements (3 инстанса)**:
- **se-01**: edit mode, 1GB, priority 100, port 8010
- **se-02**: edit mode, 1GB, priority 200, port 8011
- **se-03**: rw mode, 1GB, priority 300, port 8012

**Модули**:
- Admin Module: 8000
- Ingester Module: 8020
- Query Module: 8030
- Admin UI: 4200

**Ключевые изменения**:
1. se-01, se-02: rw → edit режим
2. Размер: 100GB → 1GB (для быстрого тестирования)
3. Добавить se-03 в rw режиме
4. Отдельные БД: artstore_admin, artstore_query, se_01, se_02, se_03
5. MinIO папки: se_01/, se_02/, se_03/

---

## 📚 Ключевые API Endpoints

### OAuth 2.0 Token
```bash
POST http://localhost:8000/api/v1/auth/token
client_id: sa_prod_admin_service_66e7f458
client_secret: D#^Cj)h3e,Ih%Fnf
```

### File Upload
```bash
POST http://localhost:8020/api/v1/upload
Headers: Authorization: Bearer {token}
Form: file, retention_policy, ttl_days
```

### File Finalization
```bash
POST http://localhost:8020/api/v1/finalize/{file_id}
Headers: Authorization: Bearer {token}
```

### Health Checks
```bash
GET /health/live   (liveness)
GET /health/ready  (readiness)
```

### Prometheus Metrics
```bash
GET /metrics
# Ключевые метрики:
storage_capacity_percent_used{se="se-01"}
storage_capacity_status{se="se-01"}  # 1=ok, 2=warning, 3=critical, 4=full
storage_element_selected_total{se="se-01"}
file_finalize_total{status="success"}
storage_fallback_total{source="..."}
```

---

## 🔬 Структура тестирования

### ФАЗА 0: Pre-Flight Проверки
- Проверка документации
- Проверка API endpoints
- Проверка Prometheus метрик
- Сбор baseline метрик

### ФАЗА 1: Подготовка стенда
- Backup данных
- Очистка PostgreSQL, MinIO, Redis
- Модификация docker-compose
- Пересборка контейнеров
- Запуск инфраструктуры и модулей

### ФАЗА 2: Baseline метрики
- Snapshot метрик SE
- Проверка Redis Service Discovery
- Проверка Admin Module registry

### ФАЗА 3: Позитивные сценарии (T1-T7)
- **T1**: Базовая загрузка 40 файлов в se-01
- **T2**: Sequential Fill до 96% заполнения se-01
- **T3**: Capacity Status Transitions (OK→WARNING→CRITICAL→FULL)
- **T4**: Переключение на se-02 после FULL se-01
- **T5**: Проверка 20 новых файлов в se-02
- **T6**: File Finalization (TEMPORARY→PERMANENT migration)
- **T7**: Новые temporary файлы идут в edit SE (не в rw!)

### ФАЗА 4: Негативные сценарии (T8-T10)
- **T8**: Fallback при Redis down (Redis → Admin API)
- **T9**: Fallback при Admin down (Admin → Local Config)
- **T10**: Все Edit SE заполнены (должен использовать RW SE)

### ФАЗА 5: Валидация результатов
- Проверка MinIO содержимого
- Проверка логов на transitions
- Проверка Prometheus метрик
- Сравнение с критериями успеха

### ФАЗА 6: Cleanup и отчетность
- Генерация TEST-RESULTS.md
- Сохранение артефактов
- Rollback конфигурации

---

## 📊 Ожидаемые результаты (успех)

**Метрики**:
- se-01: 96-100% заполнено, status=FULL (4)
- se-02: 20-30% заполнено, status=OK (1)
- se-03: 2-5% заполнено, status=OK (1)
- storage_element_selected_total{se="se-01"} > 40
- file_finalize_total{status="success"} ≥ 20

**MinIO**:
- se_01/: ~100+ файлов + ~100+ attr.json
- se_02/: ~20+ файлов + ~20+ attr.json
- se_03/: ~20+ файлов + ~20+ attr.json

**Логи**:
- Capacity transitions: OK → WARNING → CRITICAL → FULL
- SE selection: se-01 → se-02 → se-03
- Fallback activation: Redis → Admin → Local Config

---

## 🛠️ Требуемые скрипты

1. **generate_test_compose.sh** - Генерация docker-compose.test.yml
2. **check_prerequisites.sh** - Pre-flight проверки
3. **upload_test_files.py** - Загрузка N файлов
4. **fill_storage.py** - Заполнение SE до процента
5. **validate_health_checks.sh** - Проверка health статусов
6. **collect_baseline_metrics.sh** - Сбор baseline метрик
7. **compare_metrics.py** - Сравнение метрик
8. **generate_test_report.sh** - Генерация отчета
9. **plot_capacity_growth.py** - График capacity

---

## 🎓 Ответ на вопрос WEB UI

**Вопрос**: Контролировать WEB UI в рамках этого теста?

**Ответ**: **НЕТ, отдельный тест**

**Обоснование**:
1. Разделение областей (Backend vs Frontend)
2. Изоляция сложности (при провале будет ясно что именно)
3. Параллельная разработка (Frontend не заблокирован)
4. Отдельный E2E тест (Playwright/Cypress)

**Рекомендация**: Создать T_UI_01 "Storage Status Dashboard" после успешного Backend тестирования.

---

## ✅ Критерии завершения

### План считается выполненным когда:
- [x] Все 6 фаз завершены без критических ошибок
- [x] TEST-RESULTS.md сгенерирован
- [x] Все критерии успеха из 1stTEST.md выполнены
- [x] Дополнительные критерии (T8-T10) выполнены
- [x] Метрики и логи сохранены
- [x] Отчет проверен

### При провале теста:
1. Остановить дальнейшее выполнение
2. Записать детали ошибки в TEST-RESULTS.md
3. Сохранить состояние системы (логи, метрики)
4. Не продолжать до исправления

---

## 🚨 Потенциальные проблемы и решения

| Проблема | Решение |
|----------|---------|
| Redis timeout | `docker-compose restart redis` |
| PostgreSQL migration fail | `docker exec ... alembic upgrade head` |
| MinIO bucket not found | `mc mb minio/artstore-files` |
| JWT token expired | Получить новый token через OAuth |

---

## 📚 Ссылки на ключевые файлы

| Компонент | Файл |
|-----------|------|
| Selection Logic | `ingester-module/app/services/storage_selector.py` |
| Capacity Calculator | `storage-element/app/core/capacity_calculator.py` |
| Ingester Metrics | `ingester-module/app/core/metrics.py` |
| Storage Metrics | `storage-element/app/core/capacity_metrics.py` |
| Upload Endpoint | `ingester-module/app/api/v1/endpoints/upload.py` |
| Strategy Doc | `README.md` (строки 204-284) |
| ADR-014 | `docs/adr/014-sequential-fill-strategy.md` |

---

## ✅ Quick Checklist

### Подготовка
- [ ] Backup данных
- [ ] PostgreSQL БД созданы
- [ ] MinIO папки созданы
- [ ] Redis очищен
- [ ] docker-compose.test.yml сгенерирован
- [ ] Контейнеры пересобраны

### Тесты
- [ ] T1: 40 файлов в se-01
- [ ] T2: se-01 до 96%
- [ ] T3: Status transitions
- [ ] T4: Switch to se-02
- [ ] T5: 20 files in se-02
- [ ] T6: Finalization работает
- [ ] T7: Retention policy routing
- [ ] T8: Redis fallback
- [ ] T9: Local config fallback
- [ ] T10: All edit full

### Валидация
- [ ] MinIO: all files + attr.json
- [ ] Логи: transitions записаны
- [ ] Метрики: соответствуют ожиданиям
- [ ] TEST-RESULTS.md сгенерирован
- [ ] Артефакты сохранены

---

**Конец плана тестирования v2.0**

**Версия**: 2.0
**Дата**: 2025-12-03
**Статус**: Ready for Execution
**Автор**: Claude Code (Senior QA Engineer Mode)
