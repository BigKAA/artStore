#!/usr/bin/env bash
# Запуск одного модуля локально с подключением к K8s инфраструктуре
# Использование:
#   ./dev-local.sh admin-module
#   ./dev-local.sh ingester-module
#   ./dev-local.sh query-module
#   ./dev-local.sh storage-element
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "Использование: $0 <module-name>"
  echo "  module-name: admin-module | ingester-module | query-module | storage-element"
  exit 1
fi

MODULE="$1"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
NAMESPACE="artstore"

echo "=== Настройка port-forward для K8s сервисов ==="

# Убиваем старые port-forward при выходе
cleanup() {
  echo ""
  echo "Остановка port-forward..."
  kill $(jobs -p) 2>/dev/null || true
}
trap cleanup EXIT

# Port-forward инфраструктурных сервисов
kubectl port-forward -n "${NAMESPACE}" svc/postgres 5432:5432 &
kubectl port-forward -n "${NAMESPACE}" svc/redis 6379:6379 &
kubectl port-forward -n "${NAMESPACE}" svc/minio 9000:9000 &

# Port-forward app-модулей (кроме того, что запускаем локально)
if [[ "${MODULE}" != "admin-module" ]]; then
  kubectl port-forward -n "${NAMESPACE}" svc/admin-module 8000:8000 &
fi
if [[ "${MODULE}" != "ingester-module" ]]; then
  kubectl port-forward -n "${NAMESPACE}" svc/ingester-module 8020:8020 &
fi
if [[ "${MODULE}" != "query-module" ]]; then
  kubectl port-forward -n "${NAMESPACE}" svc/query-module 8030:8030 &
fi

sleep 2
echo ""
echo "=== Port-forward запущен ==="

# Генерация .env для локального запуска
ENV_FILE="${PROJECT_ROOT}/${MODULE}/.env.dev-remote"
cat > "${ENV_FILE}" << 'ENVEOF'
# Автогенерированный файл для локальной разработки с K8s инфраструктурой
# НЕ коммитить!

# Database (через port-forward)
DB_HOST=localhost
DB_PORT=5432
DB_USERNAME=artstore
DB_PASSWORD=password

# Redis (через port-forward)
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0
REDIS_URL=redis://localhost:6379/0

# MinIO (через port-forward)
STORAGE_S3_ENDPOINT_URL=http://localhost:9000
STORAGE_S3_ACCESS_KEY_ID=minioadmin
STORAGE_S3_SECRET_ACCESS_KEY=minioadmin
STORAGE_S3_BUCKET_NAME=artstore-files
STORAGE_S3_REGION=us-east-1

# JWT
JWT_ALGORITHM=RS256

# Admin Module URL
AUTH_ADMIN_MODULE_URL=http://localhost:8000
SERVICE_ACCOUNT_ADMIN_MODULE_URL=http://localhost:8000

# Service Discovery
SERVICE_DISCOVERY_CHANNEL=artstore:storage-elements

# Logging
LOG_LEVEL=DEBUG
LOG_FORMAT=text
ENVEOF

# Дополнительные переменные в зависимости от модуля
case "${MODULE}" in
  admin-module)
    cat >> "${ENV_FILE}" << 'EOF'
DB_DATABASE=artstore_admin
APP_DEBUG=on
APP_SWAGGER_ENABLED=on
JWT_PRIVATE_KEY_PATH=./keys/private_key.pem
JWT_PUBLIC_KEY_PATH=./keys/public_key.pem
INITIAL_ACCOUNT_ENABLED=on
INITIAL_ACCOUNT_NAME=admin-service
INITIAL_ACCOUNT_PASSWORD=Test-Password123
SCHEDULER_ENABLED=on
EVENT_PUBLISH_ENABLED=on
EOF
    ;;
  ingester-module)
    cat >> "${ENV_FILE}" << 'EOF'
APP_SWAGGER_ENABLED=on
JWT_PUBLIC_KEY_PATH=./keys/public_key.pem
MAX_FILE_SIZE_MB=1024
COMPRESSION_ENABLED=on
CIRCUIT_BREAKER_ENABLED=on
SERVICE_ACCOUNT_CLIENT_ID=sa_prod_admin_service_49816ff2
SERVICE_ACCOUNT_CLIENT_SECRET=Test-Password123
EOF
    ;;
  query-module)
    cat >> "${ENV_FILE}" << 'EOF'
DB_DATABASE=artstore_query
APP_SWAGGER_ENABLED=on
JWT_PUBLIC_KEY_PATH=./keys/public_key.pem
EVENT_SUBSCRIBE_ENABLED=on
CIRCUIT_BREAKER_ENABLED=on
EOF
    ;;
  storage-element)
    cat >> "${ENV_FILE}" << 'EOF'
DB_DATABASE=artstore
APP_MODE=edit
STORAGE_TYPE=s3
STORAGE_MAX_SIZE=1073741824
STORAGE_ELEMENT_ID=se-local
STORAGE_PRIORITY=100
STORAGE_S3_APP_FOLDER=storage_element_local
DB_TABLE_PREFIX=storage_elem_local
JWT_PUBLIC_KEY_PATH=./keys/public_key.pem
WAL_ENABLED=on
SERVICE_ACCOUNT_CLIENT_ID=sa_prod_admin_service_49816ff2
SERVICE_ACCOUNT_CLIENT_SECRET=Test-Password123
EOF
    ;;
esac

echo "Сгенерирован ${ENV_FILE}"
echo ""
echo "=== Запуск ${MODULE} локально с hot-reload ==="
echo ""

cd "${PROJECT_ROOT}/${MODULE}"

# Активируем venv если есть
if [[ -f "${PROJECT_ROOT}/.venv/bin/activate" ]]; then
  source "${PROJECT_ROOT}/.venv/bin/activate"
fi

# Определяем порт
case "${MODULE}" in
  admin-module)    PORT=8000 ;;
  ingester-module) PORT=8020 ;;
  query-module)    PORT=8030 ;;
  storage-element) PORT=8010 ;;
esac

# Запуск uvicorn с env-файлом
set -a
source "${ENV_FILE}"
set +a

exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT}" --reload
