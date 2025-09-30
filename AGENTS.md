# Prompts

## Описание проекта

ArtStore - распределенная система файлового хранилища с микросервисной архитектурой для долгосрочного хранения документов.

### Структура модулей

Проект состоит из модулей backend и UI на Angular:

- **admin-module** - backend административного модуля (центр управления, аутентификации, координации)
- **storage-element** - backend элемента хранения (физическое хранение файлов с кластеризацией)
- **ingester-module** - backend модуля добавления, удаления и переноса файлов
- **query-module** - backend модуля поиска и получения файлов
- **admin-ui** - UI административного модуля (Angular + Bootstrap 5)

### Документация

- **README.md** (корень) - общая архитектура системы
- **HISTORY.md** - хронология развития, архитектурные решения, milestone проекта
- **README.md** (модули) - детальное описание каждого модуля
- **CLAUDE.md** - инструкции для Claude Code

Модули разрабатываются в перечисленной выше последовательности.

Для каждого модуля создается docker контейнер. Для admin-ui контейнер на базе nginx.

## Общие вопросы

Если не знаешь ответ, так и скажи - Не знаю ответ. Не ври.

Если видишь, что выполнение задач зациклилось - остановись, спроси что делать дальше.

Пиши подробные комментарии в коде на русском языке.

Учти что разработка ведется на машине с Windows 11, используй команды cmd.exe или powershell.

Отвечай на русском языке.

## Набор утилит

Базовые утилиты запущены в docker при помощи docker-compose.yml:

- postgres
- redis
- minio
- dex
- ldap

Логины и пароли администраторов приложений доступны в `docker-compose.yml`.

Для работы с postgres используй инструменты, находящиеся в контейнере postgres.

Если необходимой базы данных нет - создавай ее сам.

Используй MCP: context7 и serena.

## Ключевые архитектурные принципы

### Attribute-First Storage Model
**КРИТИЧЕСКИ ВАЖНО:** Файлы атрибутов (`*.attr.json`) являются единственным источником истины (point of truth) для метаданных файлов. Это основа приложения для облегчения backup'а элемента хранения как набора простых файлов без необходимости работы с отдельными таблицами БД.

**Протокол консистентности:**
```
WAL → Attr File → Vector Clock → DB Cache → Commit
```

### Distributed Architecture Patterns

При разработке обязательно учитывай следующие паттерны:

1. **Saga Pattern** - для долгосрочных распределенных операций:
   - Загрузка файлов (upload → validation → indexing → commit)
   - Координация через Admin Module Cluster как Saga Orchestrator
   - Compensating actions для отката при сбоях

2. **Two-Phase Commit (2PC)** - для критических операций:
   - Смена режимов storage-element
   - Перенос файлов между storage-element
   - Изменение критических метаданных

3. **Vector Clocks** - для глобального упорядочивания событий:
   - Admin Module управляет Vector Clock
   - Все модули синхронизируют логическое время
   - Обнаружение и разрешение конфликтов данных

4. **Circuit Breaker Pattern** - обязательно для всех inter-service communications:
   - Graceful degradation при недоступности dependencies
   - Exponential backoff для retry логики
   - Health monitoring всех сервисов

5. **Write-Ahead Log (WAL)** - для атомарности операций:
   - Журнал транзакций перед изменением данных
   - Rollback при сбоях
   - Гарантии консистентности

### High Availability Requirements

**Устранение всех Single Points of Failure:**

1. **Load Balancer Cluster** - HAProxy/Nginx с keepalived
2. **Admin Module Cluster** - Raft consensus, 3+ узлов, RTO < 15 сек
3. **Redis Sentinel Cluster** - 3+ Sentinel узлов, RTO < 30 сек
4. **Storage Element Clusters** - master election через Redis Sentinel

**Stateless Design:**
- Все модули без сохранения состояния
- Горизонтальное масштабирование всех компонентов
- Local fallback при недоступности Service Discovery

### Security Framework

**Обязательные требования безопасности:**

1. **TLS 1.3** - все межсервисные соединения
2. **JWT RS256** - асимметричное шифрование токенов
3. **Automated Key Rotation** - ротация ключей каждые 24 часа
4. **Fine-grained RBAC** - resource-level permissions
5. **Comprehensive Audit Logging** - tamper-proof с цифровыми подписями
6. **API Rate Limiting** - защита от DDoS
7. **Real-time Security Monitoring** - обнаружение аномалий

### Performance Optimization

**Обязательные оптимизации:**

1. **Multi-Level Caching** - CDN → Redis → Local → DB Cache
2. **PostgreSQL Full-Text Search** - встроенные GIN индексы
3. **Streaming Operations** - chunked uploads/downloads для файлов >10MB
4. **Connection Pooling** - HTTP/2 persistent connections
5. **Async Processing** - Kafka для heavy operations
6. **Background Tasks** - асинхронная индексация и compression

### Monitoring и Observability

**Обязательная реализация:**

1. **OpenTelemetry Distributed Tracing:**
   - Trace correlation с уникальными trace ID
   - Span instrumentation всех операций
   - Context propagation через headers

2. **Custom Business Metrics:**
   - File operation performance
   - Search efficiency
   - Storage utilization
   - Authentication metrics
   - Cluster coordination health

3. **Third-party Integration:**
   - Prometheus metrics export
   - Structured logging (JSON)
   - External APM systems (Jaeger, Zipkin)

## Важные технические детали

### Режимы работы Storage Element

- **edit** - полный CRUD (режим не меняется через API)
- **rw** - read-write, удаление запрещено (можно перевести в ro)
- **ro** - read-only (можно перевести в ar)
- **ar** - archive, только метаданные (смена режима только через config + restart)

### Master Election для Storage Element

- Для режимов **edit** и **rw** требуется master election через Redis Sentinel
- Automatic failover при недоступности мастера < 30 секунд
- Split-brain protection через кворумные решения

### Service Discovery через Redis Sentinel

- Admin Module Cluster публикует конфигурацию storage-element
- Ingester/Query подписываются на обновления через Redis Sentinel
- Local configuration fallback при недоступности Redis
- Exponential backoff retry при временных сбоях

## Запуск приложений и отладка

Для запуска приложений используй `docker-compose-app.yml` в корне проекта.

Для конфигурации приложений в `docker-compose-app.yml` используй переменные среды окружения.

Если были изменения в коде, обязательно пересобирай контейнер перед запуском.

Если запускается несколько контейнеров одного и того-же приложения - используй один образ, а не отдельный образ для каждого.

Доступ к LDAP серверу: `-H ldap://localhost:3389` `-D "cn=Directory Manager"` `-w 'password'`

Тестовый пользователь логин admin пароль admin123

## Тестирование приложений

После написания кода приложений всегда создавай и запускай unit tests для измененного кода.
