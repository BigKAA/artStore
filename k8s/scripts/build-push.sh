#!/usr/bin/env bash
# Сборка Docker-образов и push в локальный registry
# Использование:
#   ./build-push.sh              # собрать все модули
#   ./build-push.sh admin-module # собрать один модуль
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
CHARTS_DIR="${SCRIPT_DIR}/../charts"
VALUES_DIR="${SCRIPT_DIR}/../values"

REGISTRY="${REGISTRY:-harbor.kryukov.lan/library}"
TAG="${TAG:-latest}"
NAMESPACE="${NAMESPACE:-artstore}"
PLATFORM="${PLATFORM:-linux/amd64}"

MODULES=(admin-module ingester-module query-module storage-element)

if [[ $# -gt 0 ]]; then
  MODULES=("$@")
fi

echo "=== ArtStore: сборка образов ==="
echo "Registry:  ${REGISTRY}"
echo "Tag:       ${TAG}"
echo "Platform:  ${PLATFORM}"
echo "Модули:    ${MODULES[*]}"
echo ""

for module in "${MODULES[@]}"; do
  image="${REGISTRY}/${module}:${TAG}"
  echo "--- Сборка ${module} → ${image} ---"
  docker build --platform "${PLATFORM}" -t "${image}" -f "${PROJECT_ROOT}/${module}/Dockerfile" "${PROJECT_ROOT}/${module}"
  echo "--- Push ${image} ---"
  docker push "${image}"
  echo ""
done

# Создание namespace (идемпотентно)
kubectl create namespace "${NAMESPACE}" --dry-run=client -o yaml | kubectl apply -f -

# JWT keys Secret
echo "=== Проверка jwt-keys Secret ==="
if ! kubectl get secret jwt-keys -n "${NAMESPACE}" &>/dev/null; then
  KEYS_DIR="${PROJECT_ROOT}/storage-element/keys"
  if [[ -f "${KEYS_DIR}/private_key.pem" && -f "${KEYS_DIR}/public_key.pem" ]]; then
    echo "Создание jwt-keys Secret..."
    kubectl create secret generic jwt-keys \
      --from-file=private_key.pem="${KEYS_DIR}/private_key.pem" \
      --from-file=public_key.pem="${KEYS_DIR}/public_key.pem" \
      -n "${NAMESPACE}"
  else
    echo "ВНИМАНИЕ: JWT ключи не найдены в ${KEYS_DIR}"
  fi
else
  echo "jwt-keys Secret уже существует."
fi

echo ""
echo "=== Готово. Деплой (из корня проекта): ==="
echo ""
echo "# 1. Инфраструктура (MinIO + Gateway + Secrets/ConfigMap):"
echo "  helm upgrade --install infra ./k8s/charts/infrastructure -n artstore"
echo ""
echo "# 2. Модули (admin-module первым — от него зависят остальные):"
echo "  helm upgrade --install admin-module ./k8s/charts/admin-module -n artstore"
echo "  helm upgrade --install ingester ./k8s/charts/ingester-module -n artstore"
echo "  helm upgrade --install query ./k8s/charts/query-module -n artstore"
echo ""
echo "# 3. Storage Elements (по одному release на инстанс):"
echo "  helm upgrade --install se-01 ./k8s/charts/storage-element -f ./k8s/values/se-01.yaml -n artstore"
echo "  helm upgrade --install se-02 ./k8s/charts/storage-element -f ./k8s/values/se-02.yaml -n artstore"
echo "  helm upgrade --install se-03 ./k8s/charts/storage-element -f ./k8s/values/se-03.yaml -n artstore"
