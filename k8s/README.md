# Kubernetes Dev Environment для ArtStore

## Кластер

| Параметр | Значение |
|----------|----------|
| Ноды | pr1-pr4.kryukov.local (4 шт.) |
| K8s | v1.34.1, kubeadm, containerd |
| OS | Rocky Linux 10 |
| CNI | Calico |
| GatewayClass | `eg` (Envoy Gateway) |
| StorageClass | `nfs-client` (provisioner: kryukov.local/nfs) |
| MetalLB | IP pool `192.168.218.180-190` |
| Дополнительно | Cert-Manager, ArgoCD |

## Структура файлов

```
k8s/
├── registry/                      # Docker Registry (plain YAML, разовая настройка)
│   ├── deployment.yaml
│   ├── service.yaml
│   ├── pvc.yaml
│   └── httproute.yaml
├── charts/
│   ├── infrastructure/            # PostgreSQL, Redis, MinIO, Gateway, Secrets, ConfigMap
│   ├── admin-module/              # Admin Module
│   ├── ingester-module/           # Ingester Module
│   ├── query-module/              # Query Module
│   └── storage-element/           # Storage Element (1 инстанс = 1 helm release)
├── values/
│   ├── se-01.yaml                 # SE-01: edit, priority 100, 1GB
│   ├── se-02.yaml                 # SE-02: edit, priority 200, 1GB
│   └── se-03.yaml                 # SE-03: rw, priority 300, 2GB
├── scripts/
│   ├── build-push.sh              # Сборка образов и push в registry
│   ├── generate-jwt-keys.sh       # Генерация RSA ключей и K8s Secret jwt-keys
│   └── dev-local.sh               # Локальная разработка одного модуля
└── README.md
```

## Зависимости между charts

```
infrastructure    (namespace, Secrets, ConfigMap, Gateway, PostgreSQL, Redis, MinIO)
     │
     ├── admin-module         (использует: db-credentials, artstore-infra-config, jwt-keys)
     │       │
     │       ├── ingester-module    (использует: artstore-infra-config, jwt-keys)
     │       ├── query-module       (использует: db-credentials, artstore-infra-config, jwt-keys)
     │       └── storage-element x3 (используют: db-credentials, minio-credentials, artstore-infra-config, jwt-keys)
```

**Порядок деплоя**: infrastructure → admin-module → остальные модули (параллельно).

Infrastructure создаёт ресурсы, от которых зависят все модули:
- ConfigMap `artstore-infra-config` — адреса PostgreSQL, Redis, MinIO, Admin Module
- Secret `db-credentials` — логин/пароль PostgreSQL
- Secret `minio-credentials` — ключи доступа MinIO
- Secret `jwt-keys` — создаётся скриптом `build-push.sh` из файлов `storage-element/keys/`

## Быстрый старт

Все команды выполняются из корня проекта.

### 1. Docker Registry (разово)

```bash
kubectl create namespace docker-registry
kubectl apply -f k8s/registry/
```

На рабочей машине (где выполняется `docker build`) настроить insecure registry:

```bash
# /etc/docker/daemon.json
{ "insecure-registries": ["192.168.218.136:30500"] }

# Перезапустить Docker
sudo systemctl restart docker

# Добавить DNS/hosts запись для registry.local → IP Gateway из MetalLB
```

> **Примечание**: сборка образов выполняется на рабочей машине (MacBook/стационар) через Docker.
> На нодах кластера используется containerd — он скачивает образы из registry напрямую.

### 2. Сборка и push образов

```bash
# Все модули
./k8s/scripts/build-push.sh

# Один модуль
./k8s/scripts/build-push.sh admin-module

# Переопределение registry/tag
REGISTRY=192.168.218.180:5000 TAG=v0.2.0 ./k8s/scripts/build-push.sh
```

Скрипт также создаёт namespace `artstore` и Secret `jwt-keys` (из `storage-element/keys/`).

### 3. Генерация JWT ключей (один раз)

```bash
# Генерация RSA ключей и создание Secret jwt-keys
./k8s/scripts/generate-jwt-keys.sh

# Проверка
kubectl get secret jwt-keys -n artstore
```

> **Примечание**: Скрипт `build-push.sh` также создаёт этот Secret автоматически,
> если ключи уже существуют в `storage-element/keys/`. Данный скрипт нужен
> для первоначальной генерации ключей или их пересоздания (`--force`).

### 4. Деплой инфраструктуры (один раз)

```bash
helm upgrade --install infra ./k8s/charts/infrastructure
```

Проверка:
```bash
kubectl get pods -n artstore
# postgres, redis, minio — должны быть Running
```

### 5. Деплой модулей

```bash
# Admin Module — первым (от него зависят ingester и storage-element)
helm upgrade --install admin-module ./k8s/charts/admin-module

# Остальные модули — в любом порядке
helm upgrade --install ingester ./k8s/charts/ingester-module
helm upgrade --install query ./k8s/charts/query-module

# Storage Elements — по одному helm release на каждый инстанс
helm upgrade --install se-01 ./k8s/charts/storage-element -f ./k8s/values/se-01.yaml
helm upgrade --install se-02 ./k8s/charts/storage-element -f ./k8s/values/se-02.yaml
helm upgrade --install se-03 ./k8s/charts/storage-element -f ./k8s/values/se-03.yaml
```

### 6. Проверка

```bash
# Поды
kubectl get pods -n artstore

# Сервисы
kubectl get svc -n artstore

# Gateway и маршруты
kubectl get gateway -n artstore
kubectl get httproute -n artstore

# Health check
kubectl port-forward -n artstore svc/admin-module 8000:8000
curl http://localhost:8000/health/live
```

## Доступ к сервисам

### Через Gateway API

Gateway `artstore-gateway` получит IP от MetalLB. Узнать IP:

```bash
kubectl get gateway -n artstore -o jsonpath='{.items[0].status.addresses[0].value}'
```

Добавить в `/etc/hosts` на рабочей машине:

```
<GATEWAY-IP>  artstore.kryukov.lan
```

После этого:
```bash
curl http://artstore.kryukov.lan/api/auth/token    # Admin Module
curl http://artstore.kryukov.lan/api/upload         # Ingester Module
curl http://artstore.kryukov.lan/api/search         # Query Module
```

### Через port-forward (без Gateway)

```bash
kubectl port-forward -n artstore svc/admin-module 8000:8000
kubectl port-forward -n artstore svc/ingester-module 8020:8020
kubectl port-forward -n artstore svc/query-module 8030:8030
kubectl port-forward -n artstore svc/minio 9001:9001   # MinIO Console
```

## Управление Storage Elements

Каждый SE — отдельный helm release. Это позволяет добавлять, удалять и менять конфигурацию инстансов независимо.

```bash
# Добавить новый SE
cat > k8s/values/se-04.yaml << 'EOF'
elementId: se-04
mode: ro
priority: 400
maxSize: 5368709120
s3Folder: storage_element_04
dbTablePrefix: storage_elem_04
EOF
helm upgrade --install se-04 ./k8s/charts/storage-element -f ./k8s/values/se-04.yaml

# Изменить параметры существующего SE (например, перевести в ro)
# Отредактировать k8s/values/se-02.yaml, затем:
helm upgrade se-02 ./k8s/charts/storage-element -f ./k8s/values/se-02.yaml

# Удалить SE
helm uninstall se-03

# Список всех SE releases
helm list | grep ^se-
```

## Обновление модулей

```bash
# Пересобрать образ одного модуля
./k8s/scripts/build-push.sh ingester-module

# Перезапустить deployment (pull новый образ с тем же тегом)
kubectl rollout restart deployment/ingester-module -n artstore

# Или обновить через helm (при изменении values)
helm upgrade ingester ./k8s/charts/ingester-module --set logLevel=INFO
```

## Локальная разработка

Запуск одного модуля локально с hot-reload, остальные работают в K8s:

```bash
./k8s/scripts/dev-local.sh admin-module
```

Скрипт автоматически:
1. Настраивает `kubectl port-forward` к PostgreSQL, Redis, MinIO и другим модулям в K8s
2. Генерирует `.env.dev-remote` в директории модуля
3. Активирует Python venv (если есть `.venv/`)
4. Запускает `uvicorn` с `--reload` на соответствующем порту

Доступные модули: `admin-module`, `ingester-module`, `query-module`, `storage-element`.

## Проверка шаблонов Helm

```bash
# Рендер шаблонов без деплоя
helm template infra ./k8s/charts/infrastructure
helm template admin-module ./k8s/charts/admin-module
helm template se-01 ./k8s/charts/storage-element -f ./k8s/values/se-01.yaml

# Dry-run (проверка с подключением к кластеру)
helm upgrade --install infra ./k8s/charts/infrastructure --dry-run

# Логи конкретного модуля
kubectl logs -n artstore -l app.kubernetes.io/name=admin-module -f
kubectl logs -n artstore -l app.kubernetes.io/name=storage-element -f
```

## Gateway API

- Chart `infrastructure` создаёт Gateway `artstore-gateway` с `gatewayClassName: eg` (Envoy Gateway)
- MetalLB назначает IP из пула `192.168.218.180-190`
- Каждый модуль (admin, ingester, query) создаёт свой HTTPRoute к этому Gateway
- Storage Elements не имеют HTTPRoute — доступ только внутри кластера через ClusterIP
