#!/usr/bin/env bash
# Генерация RSA ключей для JWT и создание K8s Secret jwt-keys
# Использование:
#   ./generate-jwt-keys.sh              # генерация + создание Secret
#   ./generate-jwt-keys.sh --force      # пересоздать Secret даже если существует
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
KEYS_DIR="${PROJECT_ROOT}/storage-element/keys"
NAMESPACE="${NAMESPACE:-artstore}"
FORCE=false

if [[ "${1:-}" == "--force" ]]; then
  FORCE=true
fi

echo "=== Генерация JWT RSA ключей ==="

# Создание директории для ключей
mkdir -p "${KEYS_DIR}"

# Генерация ключей если их нет или --force
if [[ ! -f "${KEYS_DIR}/private_key.pem" || "${FORCE}" == "true" ]]; then
  echo "Генерация RSA 2048 key pair..."
  openssl genrsa -out "${KEYS_DIR}/private_key.pem" 2048
  openssl rsa -in "${KEYS_DIR}/private_key.pem" -pubout -out "${KEYS_DIR}/public_key.pem"
  echo "Ключи сохранены в ${KEYS_DIR}/"
else
  echo "Ключи уже существуют в ${KEYS_DIR}/. Используйте --force для пересоздания."
fi

# Создание namespace (идемпотентно)
kubectl create namespace "${NAMESPACE}" --dry-run=client -o yaml | kubectl apply -f -

# Создание/обновление K8s Secret
echo ""
echo "=== Создание jwt-keys Secret в namespace ${NAMESPACE} ==="

if kubectl get secret jwt-keys -n "${NAMESPACE}" &>/dev/null; then
  if [[ "${FORCE}" == "true" ]]; then
    echo "Удаление существующего jwt-keys Secret..."
    kubectl delete secret jwt-keys -n "${NAMESPACE}"
  else
    echo "jwt-keys Secret уже существует. Используйте --force для пересоздания."
    exit 0
  fi
fi

kubectl create secret generic jwt-keys \
  --from-file=private_key.pem="${KEYS_DIR}/private_key.pem" \
  --from-file=public_key.pem="${KEYS_DIR}/public_key.pem" \
  -n "${NAMESPACE}"

echo ""
echo "=== Готово ==="
echo "Secret jwt-keys создан в namespace ${NAMESPACE}"
echo ""
echo "Проверка:"
echo "  kubectl get secret jwt-keys -n ${NAMESPACE}"
echo "  kubectl describe secret jwt-keys -n ${NAMESPACE}"
