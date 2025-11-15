# ArtStore Monitoring Stack

Комплексная система мониторинга для всех микросервисов ArtStore на основе Prometheus + Grafana.

## Компоненты

### Prometheus (http://localhost:9090)
- Сбор метрик от всех микросервисов каждые 15 секунд
- Alert rules для критических метрик
- 30 дней retention для метрик
- Интеграция с AlertManager

### Grafana (http://localhost:3000)
- Визуализация метрик
- Предконфигурированные dashboards
- Credentials: `admin` / `admin123`

### AlertManager (http://localhost:9093)
- Управление алертами от Prometheus
- Группировка и маршрутизация уведомлений
- Webhook integration для external systems

### Node Exporter (http://localhost:9100)
- Метрики хостовой системы (CPU, Memory, Disk, Network)

## Быстрый старт

### 1. Запуск monitoring stack

```bash
# Убедиться что основная инфраструктура запущена
docker-compose up -d

# Запустить monitoring stack
docker-compose -f docker-compose.monitoring.yml up -d

# Проверить статус
docker-compose -f docker-compose.monitoring.yml ps
```

### 2. Доступ к интерфейсам

- **Prometheus**: http://localhost:9090
  - Targets: http://localhost:9090/targets
  - Alerts: http://localhost:9090/alerts
  - Graph: http://localhost:9090/graph

- **Grafana**: http://localhost:3000
  - Login: `admin` / `admin123`
  - Dashboards → ArtStore → System Overview

- **AlertManager**: http://localhost:9093
  - Alerts: http://localhost:9093/#/alerts

### 3. Проверка метрик модулей

```bash
# Admin Module
curl http://localhost:8000/metrics

# Storage Element
curl http://localhost:8010/metrics

# Ingester Module
curl http://localhost:8020/metrics

# Query Module
curl http://localhost:8030/metrics
```

## Конфигурация

### Prometheus

**File**: `prometheus/prometheus.yml`

Scrape targets для всех модулей:
- Admin Module: ports 8000-8002
- Storage Element: ports 8010-8012
- Ingester Module: ports 8020-8022
- Query Module: ports 8030-8032

### Alert Rules

**File**: `prometheus/alerts.yml`

Алерты для:
- Service availability (ServiceDown, HighErrorRate)
- Performance (HighResponseTime, HighCPUUsage, HighMemoryUsage)
- Database (ConnectionPoolExhausted, SlowQueries)
- Redis (ConnectionFailed)
- Storage (LowDiskSpace, HighFileUploadFailureRate)

### Grafana Dashboards

**Directory**: `grafana/dashboards/`

Предконфигурированные дашборды:
- **artstore-overview.json**: Общий обзор системы
  - Services Up gauge
  - HTTP requests rate by service
  - HTTP response time (p95, p99)
  - HTTP error rate (5xx)

## Метрики приложений

### OpenTelemetry метрики

Каждый модуль экспортирует стандартные OpenTelemetry метрики:

#### HTTP Server Metrics
- `http_requests_total` - Total HTTP requests
- `http_request_duration_seconds` - HTTP request latency
- `http_request_size_bytes` - HTTP request size
- `http_response_size_bytes` - HTTP response size

#### Process Metrics
- `process_cpu_seconds_total` - Total CPU time
- `process_resident_memory_bytes` - Resident memory size
- `process_open_fds` - Number of open file descriptors
- `process_max_fds` - Maximum number of open file descriptors

### Custom Business Metrics

TODO: Добавить после реализации custom metrics в модулях

## Troubleshooting

### Prometheus не видит targets

```bash
# Проверить network
docker network inspect artstore_artstore_network

# Проверить что модули запущены
docker ps | grep artstore

# Проверить metrics endpoint модуля
curl http://localhost:8000/metrics
```

### Grafana не показывает данные

1. Проверить Prometheus datasource: Configuration → Data Sources → Prometheus
2. Проверить что Prometheus собирает метрики: http://localhost:9090/targets
3. Проверить query в Grafana panel: Edit → Query

### AlertManager не отправляет alerts

1. Проверить alert rules в Prometheus: http://localhost:9090/alerts
2. Проверить AlertManager configuration: `alertmanager/alertmanager.yml`
3. Проверить webhook endpoint (если настроен)

## Production Considerations

### Security

1. **Изменить Grafana credentials**: `GF_SECURITY_ADMIN_PASSWORD` в `docker-compose.monitoring.yml`
2. **Настроить SMTP для email alerts**: раскомментировать и заполнить `global.smtp_*` в `alertmanager/alertmanager.yml`
3. **Ограничить доступ**: добавить reverse proxy с authentication

### Scaling

1. **Prometheus retention**: настроить `--storage.tsdb.retention.time` для production
2. **Grafana provisioning**: добавить больше dashboards в `grafana/dashboards/`
3. **External exporters**: добавить PostgreSQL Exporter и Redis Exporter

### Backup

```bash
# Backup Prometheus data
docker run --rm --volumes-from artstore_prometheus -v $(pwd):/backup alpine tar czf /backup/prometheus-data.tar.gz /prometheus

# Backup Grafana data
docker run --rm --volumes-from artstore_grafana -v $(pwd):/backup alpine tar czf /backup/grafana-data.tar.gz /var/lib/grafana
```

## Полезные PromQL запросы

```promql
# Top 5 endpoints по количеству запросов
topk(5, sum(rate(http_requests_total[5m])) by (handler))

# Средний response time по сервисам
avg(rate(http_request_duration_seconds_sum[5m]) / rate(http_request_duration_seconds_count[5m])) by (service)

# Error rate по эндпоинтам
sum(rate(http_requests_total{status=~"5.."}[5m])) by (handler) / sum(rate(http_requests_total[5m])) by (handler)

# Memory usage всех сервисов
sum(process_resident_memory_bytes) by (service) / 1024 / 1024
```
