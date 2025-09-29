# ArtStore Ingester

Модуль для добавления и управления файлами в распределенном хранилище ArtStore.

## Функциональность

### Высокопроизводительные файловые операции
- **Streaming Upload**: Chunked загрузка больших файлов с progress tracking и resumable uploads
- **Parallel Processing**: Одновременная загрузка множественных файлов с connection pooling
- **Compression On-the-fly**: Автоматическое сжатие файлов (Brotli/GZIP) при загрузке

### Основные операции с файлами
- **Добавление файлов**: Загружает файлы в storage_element с использованием **Saga транзакций** для обеспечения консистентности. В API запросе должен указываться целевой режим storage_element.
- **Удаление файлов**: Может удалять файлы только из storage_element в режиме edit с **компенсирующими операциями** для отката в случае сбоя.
- **Перенос файлов**: Переносит файлы из storage_element в режиме edit в storage_element в режиме rw с использованием **Two-Phase Commit** протокола.

### Мониторинг и координация
- **Saga Participant**: Участвует в распределенных транзакциях, координируемых Admin Module Cluster
- **Vector Clock Sync**: Синхронизирует логическое время с другими компонентами системы
- **Redis Sentinel Integration**: Подключение к кластеру Redis Sentinel для устранения SPOF
- **Circuit Breaker Pattern**: Автоматическое отключение недоступных dependencies с graceful degradation
- **Local Configuration Fallback**: Переход на кешированную конфигурацию при недоступности Service Discovery
- **Exponential Backoff Retry**: Интеллектуальные повторы при временных сбоях
- **Web interface**: Показывает текущую конфигурацию модуля и состояние, полученное из Service Discovery.
- **Stateless кластерная архитектура**: Модули автоматически масштабируются и балансируются через Load Balancer Cluster.

### Дополнительные возможности
- **Добавление цифровой подписи**: При необходимости использует модуль ЭЦП для создания цифровой подписи. Файл с цифровой подписью сохраняется рядом с основным файлом.
- **Проверка доступности**: Не может загрузить файл в storage_element, если он не помещается в хранилище.

## Режимы работы storage_element

В системе предполагается одновременная работа:
- **Один storage_element в режиме edit** - для активной записи новых файлов
- **Один storage_element в режиме rw** - для чтения и записи существующих файлов

### API операции по режимам
- **Режим edit**: добавление новых файлов, удаление файлов, перенос файлов в режим rw
- **Режим rw**: добавление файлов (при указании в запросе), чтение файлов

## Взаимодействие с другими модулями

- **admin_module**: Взаимодействует для получения публичного ключа для валидации JWT.
- **Service Discovery (Redis)**: Получает конфигурацию и состояние `storage_element`.
- **storage_element**: Прямое взаимодействие через API для всех файловых операций.
- **Модуль ЭЦП**: Создание цифровых подписей (опционально)

## Технологии

### Основной стек
- **Python 3.12+** с uvloop для высокой производительности
- **FastAPI** - async веб-фреймворк с HTTP/2 support
- **aiofiles** - асинхронные файловые операции

### Производительность и оптимизация
- **HTTP/2** persistent connections к storage-element
- **Connection pooling** с автоматическим управлением
- **Background tasks** для heavy operations (сжатие, индексация)
- **Brotli/GZIP** compression middleware

### Интеграции
- **Apache Kafka** для асинхронной обработки файлов
- **Redis Cluster** для кеширования метаданных
- **Background Tasks** для асинхронного обновления индексов

### Мониторинг
- **Prometheus metrics** для производительности
- **OpenTelemetry** для distributed tracing
- **Health checks** с circuit breaker pattern

### UI
- **Bootstrap 5** - UI фреймворк с progressive enhancement

## Конфигурация приложения

- Конфигурационный файл
- Переменные среды окружения.
- Переменные среды окружения имеют приоритет перед конфигурационным файлом.

## Аутентификация/авторизация пользователей

- Аутентификация/авторизация пользователей по Bearer token.
  - Все запросы к модулю должны быть аутентифицированы с помощью **JWT (RS256)**.
  - Модуль **локально** валидирует токен, используя публичный ключ `admin-module`.
  - Предусмотрен режим работы **без аутентификации** для упрощенных сценариев, который включается в конфигурации. В этом режиме административные API недоступны.

### Комплексная система безопасности

#### Защита от DDoS атак
- **DDoS Protection**: Автоматическое обнаружение и блокировка подозрительного трафика на уровне HTTP proxy

#### TLS 1.3 Transit Encryption
- **End-to-End Encryption**: Все соединения с storage-element защищены TLS 1.3
- **Certificate Pinning**: Проверка сертификатов storage-element для защиты от MITM атак
- **Perfect Forward Secrecy**: Использование эфемерных ключей для каждой сессии
- **Encrypted File Transfer**: Дополнительное шифрование файлов в процессе передачи

#### Comprehensive Audit Logging
- **File Operation Tracking**: Детальное логирование всех операций с файлами (загрузка, удаление, перенос)
- **User Activity Monitoring**: Полный аудит действий пользователей с привязкой к JWT токенам
- **Tamper-proof Logging**: Цифровая подпись всех записей аудита для предотвращения изменений
- **Real-time Security Alerts**: Немедленные уведомления о подозрительной активности

## Права доступа

- Получение состояния приложения, Liveness и Readiness probes, status - доступен всем без авторизации.
- Остальные действия, только пользователям аутентифицированным пользователям.
- **Fine-grained Permissions**: Детализированный контроль доступа на уровне операций и storage-element
- **Temporary Access Tokens**: Поддержка временных токенов для ограниченных по времени операций

### Advanced Monitoring и Observability

#### OpenTelemetry File Operations Tracing
- **Upload Pipeline Tracing**: Полное отслеживание процесса загрузки файлов от начального запроса до финального commit
- **Storage Element Communication**: Трейсинг всех взаимодействий с storage-element включая failover scenarios
- **Saga Transaction Monitoring**: Детальное отслеживание распределенных транзакций и их компенсирующих операций
- **Performance Bottleneck Detection**: Автоматическое выявление узких мест в pipeline обработки файлов

#### Custom Business Metrics
- **File Upload Performance**: Метрики времени загрузки сегментированные по размеру файла и целевому storage-element
- **Transfer Success Rates**: Статистика успешности операций загрузки, удаления и переноса файлов
- **Storage Element Health**: Мониторинг доступности и производительности каждого storage-element
- **Queue Processing Metrics**: Статистика обработки очередей background tasks и Kafka messages

#### Third-party Analytics Integration
- **Upload Metrics Export**: Экспорт file upload metrics в Prometheus для external capacity planning
- **Performance Data**: Structured metrics для load balancing optimization через external системы
- **Failure Analysis Data**: Export failure patterns для внешних аналитических платформ
 
#### Pattern Detection
- **Unusual Upload Patterns**: Обнаружение аномальных паттернов загрузки (массовые загрузки, подозрительные типы файлов)
- **Performance Degradation Alerts**: Раннее предупреждение о снижении производительности upload операций
- **Security Incident Detection**: Автоматическое выявление потенциальных security threats в file operations

## Логирование

- Поддержка JSON и текстового формата. Формат задаётся в конфигурационном файле или переменными среды окружения.
- Настраиваемые уровни логирования.
- Ротация файлов логов.
- Структурированное логирование операций.

## WEB interface

- Показывает статус модуля (health пробы).

## Разработка

Для разработки рекомендуется:

1. Использовать виртуальное окружение Python
2. Запускать инфраструктуру через docker-compose
3. Использовать режим reload для автоперезагрузки

## Лицензия

GNU GPL 3