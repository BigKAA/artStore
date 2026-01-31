# План: Kubernetes Dev Environment для ArtStore

## Контекст
- Proxmox кластер (2 ноды x 32GB), kubeadm Kubernetes v1.34.1
- StorageClass: `nfs-client`, Gateway API + MetalLB
- **Harbor** (`harbor.kryukov.lan`) — хранилище контейнеров (заменил insecure Docker registry)
- **PostgreSQL** — кластерный, namespace `pg` (НЕ в artstore namespace)
- **Redis** — кластерный, namespace `redis` (НЕ в artstore namespace)
- Helm для управления манифестами
- Две рабочие машины: стационар (много RAM) + MacBook (16GB)
- Цель: не запускать Docker на MacBook, инфраструктура в K8s

## Структура файлов

```
k8s/
├── charts/
│   ├── infrastructure/          # MinIO + Gateway + ConfigMap + Secrets
│   │   ├── Chart.yaml
│   │   ├── values.yaml          # externalPostgres, externalRedis, minio, gateway
│   │   └── templates/
│   │       ├── _helpers.tpl
│   │       ├── namespace.yaml
│   │       ├── minio-deployment.yaml
│   │       ├── minio-service.yaml
│   │       ├── minio-pvc.yaml
│   │       ├── gateway.yaml
│   │       ├── configmap.yaml   # DB_HOST=postgresql.pg.svc, REDIS_HOST=redis-master.redis.svc
│   │       └── secrets.yaml     # db-credentials, redis-credentials, minio-credentials
│   ├── admin-module/
│   ├── ingester-module/
│   ├── query-module/
│   └── storage-element/         # 1 release = 1 инстанс
├── values/
│   ├── se-01.yaml
│   ├── se-02.yaml
│   └── se-03.yaml
├── scripts/
│   ├── build-push.sh            # Сборка и push в Harbor
│   ├── init-postgres.sql        # Создание пользователя artstore и БД
│   └── dev-local.sh             # Локальная разработка с remote infra
└── README.md
```

## Внешние зависимости (уже в кластере)

| Сервис | Namespace | Service | Credentials |
|--------|-----------|---------|-------------|
| PostgreSQL | pg | postgresql.pg.svc:5432 | artur/password (superuser), artstore/password (app) |
| Redis | redis | redis-master.redis.svc:6379 | password: qUwTt8g9it |
| Harbor | harbor | harbor.kryukov.lan (HTTPS) | admin/password |

## Workflow

### Первоначальная настройка:
1. Выполнить `k8s/scripts/init-postgres.sql` на кластерном PG
2. `./k8s/scripts/build-push.sh` — собрать и запушить образы в Harbor
3. `helm upgrade --install infra ./k8s/charts/infrastructure -n artstore --create-namespace`
4. Задеплоить модули (admin-module первым)

### Ежедневная работа:
- `./k8s/scripts/dev-local.sh admin-module` — локальная разработка
- `./k8s/scripts/build-push.sh admin-module && helm upgrade --install admin-module ./k8s/charts/admin-module -n artstore`
