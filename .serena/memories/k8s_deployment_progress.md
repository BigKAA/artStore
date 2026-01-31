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
1. **Исправить JWT валидацию в ingester-module** — токен выписывается (200), но при использовании получает 401.
   Вероятная причина: JWT key manager генерирует новые ключи в памяти при ротации, а валидация использует другие.
   Нужно исследовать код `admin-module/app/core/jwt_key_manager.py`.
2. ~~**Проверить Gateway routing**~~ ✅ Переведён на `artstore.kryukov.lan`, все HTTPRoute обновлены
3. **Redis NodePort** — создать для доступа с dev-машин (для `dev-local.sh`)
4. **DNS запись** — добавить `artstore.kryukov.lan` на DNS-сервер 192.168.218.9 (если не сделано)

## Решённые проблемы:
- ✅ DNS: `harbor.kryukov.lan` → DNS сервер 192.168.218.9, ноды используют его
- ✅ TLS: CA сертификат добавлен в containerd на нодах (`/etc/containerd/certs.d/harbor.kryukov.lan/`)
- ✅ Architecture: образы пересобраны для `linux/amd64` (MacBook собирает arm64 по умолчанию)
- ✅ MinIO bucket `artstore-files` создан
- ✅ Service account `client_id` обновлён (`sa_prod_admin_service_db0fd1af`)
- ✅ PostgreSQL: пользователь `artstore` создан, БД artstore/artstore_admin/artstore_query созданы
- ✅ PostgreSQL superuser: `postgres` / `qjkMzdJh68` (хранится в `/opt/bitnami/postgresql/secrets/postgres-password`)

## Git
- Коммит `feat(k8s): Migrate to Harbor registry and external PostgreSQL/Redis` замержен в main и запушен
