# ArtStore Query

Модуль для поиска и получения файлов из хранилища.
Информацию о текущих доступных хранилищах получает из **Service Discovery (Redis)**.

## Архитектура

### Высокая доступность
- **Кластерная развертка**: Множественные узлы Query модуля за Load Balancer Cluster
- **Redis Sentinel Integration**: Подключение к кластеру Redis Sentinel для устранения SPOF Service Discovery
- **Circuit Breaker Pattern**: Автоматическое отключение недоступных storage-element
- **Local Cache Fallback**: Кеширование результатов поиска при недоступности Service Discovery
- **Health Check Integration**: Мониторинг состояния всех dependencies

### Основная архитектура
- **Аутентификация**: Все запросы к модулю должны быть аутентифицированы с помощью **JWT (RS256)**. Модуль **локально** валидирует токен, используя публичный ключ, полученный от `admin-module`.
- **Координация**: Модуль получает актуальный список `storage-element` и их состояние из **Redis Sentinel Cluster**.

## Функциональность

### Высокопроизводительный поиск
- **PostgreSQL Full-Text Search**: Встроенные возможности поиска PostgreSQL с GIN индексами для метаданных
- **Real-time Search**: Живой поиск с auto-complete на основе кешированных метаданных
- **Faceted Search**: Фильтрация по дате, размеру, типу файла, метаданным через оптимизированные индексы
- **Search Results Caching**: Redis кеширование популярных запросов (TTL: 10 минут)
- **Simple Text Search**: Поиск по содержимому файлов через PostgreSQL text индексы

### Оптимизация производительности
- **Multi-level Caching**: Local cache → Redis → PostgreSQL Query Cache
- **Connection Pooling**: HTTP/2 persistent connections к storage-element
- **Parallel Queries**: Одновременные запросы к множественным storage-element
- **Result Streaming**: Chunked transfer для больших результатов поиска

### Основная функциональность
- **Поиск файла**: Осуществляет поиск файла по названию и его метаданным с **консистентными результатами** благодаря Vector Clock.
- **Выгрузка файла**: Позволяет скачать файл и, если необходимо, файл цифровой подписью из хранилища.
- **Conflict-aware Queries**: Обнаруживает конфликты данных между storage-element и предоставляет пользователю выбор версии.
- **Read Consistency**: Гарантирует читаемую консистентность через проверку Vector Clock метаданных.
- **Web interface**: Показывает текущую конфигурацию модуля.
- **Проверка цифровой подписи**: Если необходимо, проверяет цифровую подпись файла при помощи `Модуль ЭЦП`.

## Технологии

### Основной стек
- **Python 3.12+**
- **FastAPI** - веб-фреймворк с async/await
- **SQLAlchemy** (async) - ORM для работы с PostgreSQL
- **PostgreSQL** - база данных

### Поиск и индексирование
- **PostgreSQL Full-Text Search** - встроенный поиск с GIN индексами
- **PostgreSQL pg_trgm** - триграммы для нечеткого поиска и auto-complete
- **Background Tasks** - асинхронная индексация метаданных

### Кеширование и координация
- **Redis Cluster** - многоуровневое кеширование
- **Redis Sentinel** - высокая доступность
- **Local Cache** - in-memory кеширование

### Performance & Optimization
- **HTTP/2** - persistent connections
- **Brotli/GZIP** - сжатие ответов
- **uvloop** - высокопроизводительный event loop
- **aiodns** - асинхронное разрешение DNS

### UI
- **Bootstrap 5** - UI фреймворк

### Комплексная система безопасности

#### Secure Query Processing
- **Query Injection Protection**: Автоматическая проверка и санитизация поисковых запросов для предотвращения SQL и NoSQL инъекций
- **Access Control Filtering**: Фильтрация результатов поиска на основе прав доступа пользователя к конкретным файлам
- **Data Leakage Prevention**: Контроль доступа к метаданным файлов в зависимости от уровня авторизации

#### Secure File Download
- **Download Authorization**: Проверка прав доступа перед каждой загрузкой файла
- **Temporary Download URLs**: Генерация временных подписанных URL для безопасного скачивания
- **Content-Type Validation**: Проверка типов файлов для предотвращения загрузки вредоносного контента
- **Download Audit Trail**: Полное логирование всех операций скачивания с привязкой к пользователю

#### TLS 1.3 Transit Encryption
- **Encrypted Search Results**: Шифрование результатов поиска в transit между модулями
- **Certificate Validation**: Строгая проверка сертификатов при соединении с storage-element
- **Secure API Communication**: Защищенные каналы связи со всеми компонентами системы
- **End-to-End Security**: Сквозное шифрование от клиента до storage-element

#### Real-time Security Monitoring
- **Security Pattern Detection**: Обнаружение подозрительных паттернов в поисковых запросах
- **Brute Force Protection**: Защита от попыток перебора файлов и метаданных
- **Access Pattern Analysis**: Анализ паттернов доступа для выявления потенциальных угроз
- **Automated Incident Response**: Автоматическая блокировка подозрительных источников запросов

### Advanced Monitoring и Observability

#### OpenTelemetry Search Operations Tracing
- **Search Pipeline Tracing**: Полное отслеживание поисковых запросов от начального query до возврата результатов
- **Multi-Storage Search Correlation**: Трейсинг параллельных запросов к множественным storage-element
- **Cache Performance Monitoring**: Детальная аналитика эффективности multi-level кеширования
- **PostgreSQL Query Optimization**: Профилирование и оптимизация database queries

#### Custom Business Metrics
- **Search Performance**: Время отклика поисковых запросов сегментированное по сложности и количеству результатов
- **Search Quality Metrics**: Статистика релевантности результатов и пользовательского взаимодействия
- **Download Performance**: Метрики скорости скачивания файлов по размерам и storage-element
- **Cache Efficiency**: Hit ratios для каждого уровня кеширования (Local → Redis → PostgreSQL)

#### Third-party Analytics Integration
- **Search Metrics Export**: Экспорт search performance metrics в Prometheus для external analytics
- **Query Pattern Data**: Structured data для index optimization через external systems
- **Content Analytics**: Export popular content metrics для external cache optimization platforms


## Логирование

- Поддержка JSON и текстового формата
- Настраиваемые уровни логирования
- Ротация файлов логов
- Структурированное логирование операций

## Разработка

Для разработки рекомендуется:

1. Использовать виртуальное окружение Python
2. Запускать инфраструктуру через docker-compose
3. Использовать режим reload для автоперезагрузки
4. Настроить IDE для работы с async/await
