# ArtStore Kubernetes Deployment

Полный набор Kubernetes манифестов для развертывания распределенной системы файлового хранилища ArtStore.

## Архитектура

- **Namespace**: `artstore`
- **Аутентификация**: OAuth 2.0 Client Credentials (RS256 JWT)
- **Service Discovery**: Redis Cluster
- **База данных**: PostgreSQL 15 (async asyncpg)
- **Кеш**: Redis 7 (sync redis-py)
- **Объектное хранилище**: MinIO (S3-compatible)
- **Логирование**: JSON формат
- **Мониторинг**: Prometheus + Grafana

## Структура манифестов

```
k8s/
├── namespace.yaml                    # Namespace artstore
├── secrets/
│   └── secrets.yaml.example          # Шаблон секретов (скопировать в secrets.yaml)
├── infrastructure/
│   ├── postgres-statefulset.yaml     # PostgreSQL 15 StatefulSet
│   ├── redis-statefulset.yaml        # Redis 7 StatefulSet
│   └── minio-deployment.yaml         # MinIO Deployment
├── admin-module/
│   ├── deployment.yaml               # Admin Module Deployment
│   ├── service.yaml                  # Admin Module Service
│   └── configmap.yaml                # Admin Module ConfigMap
├── storage-element/
│   ├── deployment.yaml               # Storage Element Deployment
│   ├── service.yaml                  # Storage Element Service
│   └── configmap.yaml                # Storage Element ConfigMap
├── ingester-module/
│   ├── deployment.yaml               # Ingester Module Deployment
│   ├── service.yaml                  # Ingester Module Service
│   └── configmap.yaml                # Ingester Module ConfigMap
├── query-module/
│   ├── deployment.yaml               # Query Module Deployment
│   ├── service.yaml                  # Query Module Service
│   └── configmap.yaml                # Query Module ConfigMap
├── monitoring/
│   ├── prometheus-deployment.yaml    # Prometheus Deployment
│   └── grafana-deployment.yaml       # Grafana Deployment
└── ingress/
    └── ingress.yaml                  # Nginx Ingress для всех модулей
```

## Предварительные требования

1. **Kubernetes cluster** (v1.24+)
2. **kubectl** настроенный для работы с кластером
3. **Nginx Ingress Controller** установлен в кластере
4. **Persistent Volume Provisioner** (для StatefulSets)

### Установка Nginx Ingress Controller

```bash
kubectl apply -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/controller-v1.8.2/deploy/static/provider/cloud/deploy.yaml
```

## Инструкция по развертыванию

### 1. Создание namespace

```bash
kubectl apply -f namespace.yaml
```

### 2. Настройка секретов

```bash
# Скопировать шаблон секретов
cp secrets/secrets.yaml.example secrets/secrets.yaml

# Отредактировать secrets/secrets.yaml, заменив все placeholder значения
# ВАЖНО: Изменить пароли, JWT ключи, MinIO credentials в production!
vim secrets/secrets.yaml

# Применить секреты
kubectl apply -f secrets/secrets.yaml
```

**Критически важные секреты для production**:
- `POSTGRES_PASSWORD` - пароль PostgreSQL (минимум 16 символов)
- `INITIAL_CLIENT_SECRET` - OAuth 2.0 client secret для admin-service
- `JWT_PRIVATE_KEY`, `JWT_PUBLIC_KEY` - RS256 ключи для JWT токенов
- `MINIO_ROOT_PASSWORD` - пароль MinIO

### 3. Развертывание инфраструктуры

```bash
# PostgreSQL
kubectl apply -f infrastructure/postgres-statefulset.yaml

# Redis
kubectl apply -f infrastructure/redis-statefulset.yaml

# MinIO
kubectl apply -f infrastructure/minio-deployment.yaml

# Проверка статуса
kubectl get pods -n artstore
kubectl get pvc -n artstore
```

**Ожидание готовности**:
```bash
kubectl wait --for=condition=ready pod -l app=postgres -n artstore --timeout=300s
kubectl wait --for=condition=ready pod -l app=redis -n artstore --timeout=300s
kubectl wait --for=condition=ready pod -l app=minio -n artstore --timeout=300s
```

### 4. Развертывание backend модулей

**Порядок развертывания** (важно!):

```bash
# 1. Admin Module (центр аутентификации)
kubectl apply -f admin-module/configmap.yaml
kubectl apply -f admin-module/deployment.yaml
kubectl apply -f admin-module/service.yaml

# Проверка готовности Admin Module
kubectl wait --for=condition=ready pod -l app=admin-module -n artstore --timeout=300s

# 2. Storage Element
kubectl apply -f storage-element/configmap.yaml
kubectl apply -f storage-element/deployment.yaml
kubectl apply -f storage-element/service.yaml

# 3. Ingester Module
kubectl apply -f ingester-module/configmap.yaml
kubectl apply -f ingester-module/deployment.yaml
kubectl apply -f ingester-module/service.yaml

# 4. Query Module
kubectl apply -f query-module/configmap.yaml
kubectl apply -f query-module/deployment.yaml
kubectl apply -f query-module/service.yaml

# Проверка всех модулей
kubectl get pods -n artstore -l component=backend
```

### 5. Развертывание мониторинга

```bash
# Prometheus
kubectl apply -f monitoring/prometheus-deployment.yaml

# Grafana
kubectl apply -f monitoring/grafana-deployment.yaml

# Проверка статуса
kubectl get pods -n artstore -l component=monitoring
```

### 6. Настройка Ingress

```bash
# Применить Ingress правила
kubectl apply -f ingress/ingress.yaml

# Получить External IP
kubectl get ingress -n artstore
```

## Проверка развертывания

### Health Checks

```bash
# Admin Module
kubectl exec -n artstore deployment/admin-module -- curl -f http://localhost:8000/health/live
kubectl exec -n artstore deployment/admin-module -- curl -f http://localhost:8000/health/ready

# Storage Element
kubectl exec -n artstore deployment/storage-element -- curl -f http://localhost:8010/health/live

# Ingester Module
kubectl exec -n artstore deployment/ingester-module -- curl -f http://localhost:8020/health/live

# Query Module
kubectl exec -n artstore deployment/query-module -- curl -f http://localhost:8030/health/live
```

### Prometheus Metrics

```bash
# Проверка метрик для всех модулей
for module in admin-module storage-element ingester-module query-module; do
  echo "=== $module metrics ==="
  kubectl exec -n artstore deployment/$module -- curl -s http://localhost:8000/metrics | head -20
done
```

### Логи модулей

```bash
# Просмотр логов (JSON формат)
kubectl logs -n artstore -l app=admin-module --tail=50
kubectl logs -n artstore -l app=storage-element --tail=50
kubectl logs -n artstore -l app=ingester-module --tail=50
kubectl logs -n artstore -l app=query-module --tail=50
```

## Доступ к сервисам

### Через Ingress (рекомендуется)

Предполагается DNS записи указывают на External IP Ingress Controller:

- **Admin Module**: http://artstore.example.com/api/admin/
- **Storage Element**: http://artstore.example.com/api/storage/
- **Ingester Module**: http://artstore.example.com/api/ingester/
- **Query Module**: http://artstore.example.com/api/query/
- **Prometheus**: http://artstore.example.com/prometheus/
- **Grafana**: http://artstore.example.com/grafana/

### Через Port Forwarding (для тестирования)

```bash
# Admin Module
kubectl port-forward -n artstore svc/admin-module 8000:8000

# Storage Element
kubectl port-forward -n artstore svc/storage-element 8010:8010

# Ingester Module
kubectl port-forward -n artstore svc/ingester-module 8020:8020

# Query Module
kubectl port-forward -n artstore svc/query-module 8030:8030

# Prometheus
kubectl port-forward -n artstore svc/prometheus 9090:9090

# Grafana
kubectl port-forward -n artstore svc/grafana 3000:3000

# MinIO Console
kubectl port-forward -n artstore svc/minio 9001:9001
```

## OAuth 2.0 Аутентификация

### Получение JWT токена

```bash
# Получить client_id и client_secret из secrets
CLIENT_ID=$(kubectl get secret artstore-secrets -n artstore -o jsonpath='{.data.INITIAL_CLIENT_ID}' | base64 -d)
CLIENT_SECRET=$(kubectl get secret artstore-secrets -n artstore -o jsonpath='{.data.INITIAL_CLIENT_SECRET}' | base64 -d)

# Запрос JWT токена
curl -X POST http://artstore.example.com/api/admin/auth/token \
  -H "Content-Type: application/json" \
  -d "{\"client_id\": \"$CLIENT_ID\", \"client_secret\": \"$CLIENT_SECRET\"}"

# Response: {"access_token": "eyJ...", "token_type": "Bearer", "expires_in": 1800}
```

### Использование токена

```bash
TOKEN="eyJ..."  # Из предыдущего запроса

# Пример: получение списка storage elements
curl -H "Authorization: Bearer $TOKEN" \
  http://artstore.example.com/api/admin/storage-elements/
```

## Масштабирование

### Ручное масштабирование

```bash
# Увеличить количество реплик Admin Module до 3
kubectl scale deployment admin-module -n artstore --replicas=3

# Увеличить количество реплик Query Module до 4
kubectl scale deployment query-module -n artstore --replicas=4

# Проверка статуса
kubectl get deployment -n artstore
```

### Рекомендации по масштабированию

- **Admin Module**: 2-3 реплики (не требует интенсивного масштабирования)
- **Storage Element**: 2-4 реплики (зависит от количества storage backends)
- **Ingester Module**: 3-10 реплик (зависит от нагрузки загрузки файлов)
- **Query Module**: 3-10 реплик (зависит от нагрузки поиска/скачивания)

## Обновление приложения

### Rolling Update

```bash
# Обновление образа для Admin Module
kubectl set image deployment/admin-module -n artstore \
  admin-module=artstore/admin-module:v2.0.0

# Проверка статуса обновления
kubectl rollout status deployment/admin-module -n artstore

# Откат к предыдущей версии при проблемах
kubectl rollout undo deployment/admin-module -n artstore
```

## Резервное копирование

### PostgreSQL Backup

```bash
# Создание backup через pg_dump
kubectl exec -n artstore postgres-0 -- \
  pg_dump -U artstore artstore > backup-$(date +%Y%m%d).sql

# Восстановление из backup
kubectl exec -i -n artstore postgres-0 -- \
  psql -U artstore artstore < backup-20250116.sql
```

### Redis Backup

```bash
# Создание RDB snapshot
kubectl exec -n artstore redis-0 -- redis-cli BGSAVE

# Копирование snapshot
kubectl cp artstore/redis-0:/data/dump.rdb ./redis-backup-$(date +%Y%m%d).rdb
```

### MinIO Backup

```bash
# Использовать MinIO Client (mc) для backup
kubectl run -n artstore mc-client --rm -it --image=minio/mc -- \
  mc mirror artstore-minio/artstore-files /backup/
```

## Мониторинг и алертинг

### Prometheus

Доступ: http://artstore.example.com/prometheus/

**Ключевые метрики**:
- `up{job="artstore-modules"}` - статус всех модулей
- `http_requests_total` - общее количество HTTP запросов
- `http_request_duration_seconds` - латентность запросов
- `process_resident_memory_bytes` - использование памяти

### Grafana

Доступ: http://artstore.example.com/grafana/ (admin / admin123)

**Dashboards**:
- **ArtStore - System Overview**: общая статистика системы
- **ArtStore - Module Performance**: производительность модулей
- **ArtStore - Infrastructure**: состояние PostgreSQL, Redis, MinIO

## Troubleshooting

### Pod не запускается

```bash
# Проверка событий
kubectl describe pod -n artstore <pod-name>

# Проверка логов
kubectl logs -n artstore <pod-name>

# Проверка предыдущего контейнера (если перезапустился)
kubectl logs -n artstore <pod-name> --previous
```

### Проблемы с подключением к БД

```bash
# Проверка доступности PostgreSQL
kubectl exec -n artstore postgres-0 -- pg_isready -U artstore

# Проверка подключения из модуля
kubectl exec -n artstore deployment/admin-module -- \
  nc -zv postgres.artstore.svc.cluster.local 5432
```

### Проблемы с Redis

```bash
# Проверка доступности Redis
kubectl exec -n artstore redis-0 -- redis-cli PING

# Проверка подключения из модуля
kubectl exec -n artstore deployment/admin-module -- \
  nc -zv redis.artstore.svc.cluster.local 6379
```

### Проблемы с Persistent Volumes

```bash
# Проверка статуса PVC
kubectl get pvc -n artstore

# Проверка событий PVC
kubectl describe pvc -n artstore <pvc-name>

# Проверка Persistent Volumes
kubectl get pv
```

## Удаление развертывания

**ВНИМАНИЕ**: Удаление PVC приведет к потере всех данных!

```bash
# Удалить все ресурсы кроме PVC
kubectl delete ingress,deployment,service,configmap,statefulset -n artstore --all

# Удалить PVC (ПОТЕРЯ ДАННЫХ!)
kubectl delete pvc -n artstore --all

# Удалить secrets
kubectl delete secret -n artstore --all

# Удалить namespace
kubectl delete namespace artstore
```

## Production Checklist

Перед запуском в production убедитесь:

- ✅ Все секреты изменены с placeholder значений
- ✅ JWT ключи сгенерированы безопасно (RS256 2048+ бит)
- ✅ Настроены resource limits для всех Deployments
- ✅ Настроен Persistent Volume Provisioner
- ✅ Настроен регулярный backup PostgreSQL, Redis, MinIO
- ✅ Настроены DNS записи для Ingress
- ✅ Настроен TLS сертификат для Ingress (cert-manager)
- ✅ Настроен мониторинг и алертинг (Prometheus AlertManager)
- ✅ Протестированы health checks всех модулей
- ✅ Протестирован OAuth 2.0 authentication flow
- ✅ Настроены Network Policies (опционально)
- ✅ Проверена работоспособность Service Discovery через Redis

## Дополнительная информация

- **Документация проекта**: `/home/artur/Projects/artStore/README.md`
- **Архитектурные решения**: `/home/artur/Projects/artStore/ARCHITECTURE_DECISIONS.md`
- **План развития**: `/home/artur/Projects/artStore/DEVELOPMENT_PLAN.md`
- **Мониторинг**: `/home/artur/Projects/artStore/monitoring/README.md`
