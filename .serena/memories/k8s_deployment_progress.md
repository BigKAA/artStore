# K8s Deployment Progress — ArtStore

## Текущее состояние (2026-01-31, обновлено)

### Инфраструктура — внешние сервисы кластера
- **PostgreSQL** — кластерный, namespace `pg`, service `postgresql.pg.svc:5432`, NodePort 32543
  - Суперпользователь: `artur` / `password`
  - Пользователь для ArtStore: `artstore` / `password` (создать через `k8s/scripts/init-postgres.sql`)
  - БД: `artstore`, `artstore_admin`, `artstore_query`
  - pgAdmin: `pg.kryukov.lan`
- **Redis** — кластерный, namespace `redis`, service `redis-master.redis.svc:6379`
  - Password: `qUwTt8g9it`
- **Harbor** — хранилище контейнеров: `https://harbor.kryukov.lan`
  - Credentials: admin / password
  - Проект: `library` (публичный)

### Что сделано:
1. **Infrastructure chart** обновлён — PostgreSQL и Redis удалены (используются кластерные)
   - Остались: MinIO, Gateway, ConfigMap, Secrets (db-credentials, redis-credentials, minio-credentials)
   - ConfigMap указывает на `postgresql.pg.svc` и `redis-master.redis.svc`
2. **Registry** обновлён на Harbor (`harbor.kryukov.lan/library`)
   - Все values.yaml модулей обновлены
   - build-push.sh обновлён
   - Директория `k8s/registry/` удалена
3. **REDIS_PASSWORD** добавлен во все deployment шаблоны (secretKeyRef → redis-credentials)
4. **SQL скрипт** `k8s/scripts/init-postgres.sql` создан для инициализации пользователя и БД

### Что нужно сделать:
1. **Выполнить SQL скрипт** на кластерном PostgreSQL (создать пользователя artstore и БД)
2. **Собрать и запушить образы** в Harbor:
   ```bash
   ./k8s/scripts/build-push.sh
   ```
3. **Задеплоить infrastructure** (MinIO + Gateway + Secrets):
   ```bash
   helm upgrade --install infra ./k8s/charts/infrastructure -n artstore --create-namespace
   ```
4. **Задеплоить модули**:
   ```bash
   helm upgrade --install admin-module ./k8s/charts/admin-module -n artstore
   helm upgrade --install ingester ./k8s/charts/ingester-module -n artstore
   helm upgrade --install query ./k8s/charts/query-module -n artstore
   helm upgrade --install se-01 ./k8s/charts/storage-element -f ./k8s/values/se-01.yaml -n artstore
   helm upgrade --install se-02 ./k8s/charts/storage-element -f ./k8s/values/se-02.yaml -n artstore
   helm upgrade --install se-03 ./k8s/charts/storage-element -f ./k8s/values/se-03.yaml -n artstore
   ```
5. **Проверить** что все поды Running
6. **Проверить Gateway routing** через artstore.local

### Кластер
- 4 ноды: pr1 (control-plane), pr2-pr4 (workers), Rocky Linux 10, K8s v1.34.1, containerd 2.1.5
- IPs: 192.168.218.136-139
- GatewayClass: `eg` (Envoy Gateway)
- StorageClass: `nfs-client`
- MetalLB pool: 192.168.218.180-190
- Gateway IP: 192.168.218.181
- Namespace: artstore

### Файловая структура k8s/
```
k8s/
├── charts/
│   ├── infrastructure/ # MinIO, Gateway, Secrets, ConfigMap (PG и Redis — внешние)
│   ├── admin-module/
│   ├── ingester-module/
│   ├── query-module/
│   └── storage-element/
├── values/
│   ├── se-01.yaml
│   ├── se-02.yaml
│   └── se-03.yaml
├── scripts/
│   ├── build-push.sh
│   ├── init-postgres.sql
│   └── dev-local.sh
└── README.md
```
