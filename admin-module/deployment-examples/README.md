# Admin Module Deployment Examples

Примеры deployment конфигураций для различных платформ с использованием Platform-Agnostic Secret Management.

## Обзор

Admin Module поддерживает три метода загрузки секретов с автоматическим определением платформы:

1. **Kubernetes Secrets** (k8s/k3s) - файловые монтирования в `/var/run/secrets/artstore/`
2. **Environment Variables** (Docker Compose, development) - через `SECURITY_AUDIT_HMAC_SECRET`, `JWT_PRIVATE_KEY`, etc.
3. **File-based Secrets** (custom scenarios) - локальные файлы в `./secrets/` директории

**Fallback chain**: `k8s Secret → Environment Variable → File → Default Value`

## Docker Compose Deployment

### Быстрый старт

```bash
# 1. Создайте .env файл с секретами
cat > .env <<EOF
DB_PASSWORD=secure-postgres-password
REDIS_PASSWORD=secure-redis-password
AUDIT_HMAC_SECRET=production-hmac-secret-minimum-32-characters-required
EOF

# 2. Сгенерируйте JWT ключи
mkdir -p keys
openssl genrsa -out keys/private_key.pem 2048
openssl rsa -in keys/private_key.pem -pubout -out keys/public_key.pem

# 3. Запустите приложение
docker-compose -f docker-compose.secrets.yml up -d

# 4. Проверьте статус
docker-compose -f docker-compose.secrets.yml ps
docker-compose -f docker-compose.secrets.yml logs -f admin-module

# 5. Проверьте health endpoint
curl http://localhost:8000/health/live
```

### Environment Variables Approach

**Преимущества:**
- Простота настройки
- Нативная поддержка Docker Compose
- Совместимость с .env файлами

**Недостатки:**
- Secrets видны в `docker inspect`
- Логируются в process environment
- Менее безопасно для production

**Пример:**

```yaml
environment:
  SECURITY_AUDIT_HMAC_SECRET: "your-secure-hmac-secret-min-32-chars"
  JWT_PRIVATE_KEY_PATH: "/app/keys/private_key.pem"  # Файловый путь
  JWT_PUBLIC_KEY_PATH: "/app/keys/public_key.pem"
```

### Direct PEM Content Approach (Kubernetes-style)

**Преимущества:**
- Нет необходимости в volume mounts
- Единый подход для Docker Compose и Kubernetes
- Упрощенная конфигурация

**Недостатки:**
- Сложность с multiline environment variables
- Требуется careful escaping в docker-compose.yml

**Пример:**

```yaml
environment:
  JWT_PRIVATE_KEY: |
    -----BEGIN RSA PRIVATE KEY-----
    MIIEpAIBAAKCAQEA...
    -----END RSA PRIVATE KEY-----
  JWT_PUBLIC_KEY: |
    -----BEGIN PUBLIC KEY-----
    MIIBIjANBgkqhkiG9w0BAQEF...
    -----END PUBLIC KEY-----
```

## Kubernetes Deployment

### Быстрый старт

```bash
# 1. Создайте namespace
kubectl create namespace artstore

# 2. Сгенерируйте JWT ключи
openssl genrsa -out private_key.pem 2048
openssl rsa -in private_key.pem -pubout -out public_key.pem

# 3. Создайте Kubernetes Secret
kubectl create secret generic artstore-admin-secrets \
  --from-literal=DB_PASSWORD='secure-postgres-password' \
  --from-literal=REDIS_PASSWORD='secure-redis-password' \
  --from-literal=SECURITY_AUDIT_HMAC_SECRET='production-hmac-secret-min-32-chars' \
  --from-file=JWT_PRIVATE_KEY=./private_key.pem \
  --from-file=JWT_PUBLIC_KEY=./public_key.pem \
  --namespace=artstore

# 4. Создайте ConfigMap
kubectl apply -f kubernetes-secrets.yaml --namespace=artstore

# 5. Deploy приложение
kubectl apply -f kubernetes-deployment.yaml --namespace=artstore

# 6. Проверьте статус
kubectl get pods -n artstore
kubectl logs -f deployment/admin-module -n artstore

# 7. Проверьте health endpoint (через port-forward)
kubectl port-forward -n artstore deployment/admin-module 8000:8000
curl http://localhost:8000/health/live
```

### Secret Auto-Detection

SecretProvider автоматически определяет Kubernetes окружение:

1. Проверяет наличие `/var/run/secrets/kubernetes.io/serviceaccount/token`
2. Если найден - включает KubernetesSecretProvider
3. Читает секреты из `/var/run/secrets/artstore/`

**Внутренний алгоритм:**

```python
def is_available(self) -> bool:
    k8s_sa_token = Path("/var/run/secrets/kubernetes.io/serviceaccount/token")
    secrets_path = Path("/var/run/secrets/artstore")
    return k8s_sa_token.exists() and secrets_path.exists()
```

### Volume Mount Configuration

**В Deployment манифесте:**

```yaml
volumes:
  - name: secrets
    secret:
      secretName: artstore-admin-secrets
      items:
        - key: SECURITY_AUDIT_HMAC_SECRET
          path: SECURITY_AUDIT_HMAC_SECRET
        - key: JWT_PRIVATE_KEY
          path: JWT_PRIVATE_KEY
        - key: JWT_PUBLIC_KEY
          path: JWT_PUBLIC_KEY

containers:
  - name: admin-module
    volumeMounts:
      - name: secrets
        mountPath: /var/run/secrets/artstore
        readOnly: true
```

**Результат:**

```
/var/run/secrets/artstore/
├── SECURITY_AUDIT_HMAC_SECRET
├── JWT_PRIVATE_KEY
└── JWT_PUBLIC_KEY
```

### High Availability Setup

Deployment манифест настроен для HA:

- **Replicas**: 3 минимум (HPA scale до 10)
- **Pod Anti-Affinity**: Разносит реплики по разным нодам
- **PodDisruptionBudget**: Минимум 2 реплики всегда доступны
- **RollingUpdate**: maxSurge=1, maxUnavailable=0 (zero-downtime)
- **Health Checks**: liveness, readiness, startup probes
- **RTO**: < 15 секунд (automatic failover)

## File-based Secrets (Development)

### Использование

```bash
# 1. Создайте директорию secrets
mkdir -p ./secrets

# 2. Создайте файлы с секретами
echo "production-hmac-secret-minimum-32-characters" > ./secrets/SECURITY_AUDIT_HMAC_SECRET

# 3. Сгенерируйте JWT ключи
openssl genrsa -out ./secrets/JWT_PRIVATE_KEY 2048
openssl rsa -in ./secrets/JWT_PRIVATE_KEY -pubout -out ./secrets/JWT_PUBLIC_KEY

# 4. Установите permissions
chmod 600 ./secrets/*

# 5. Запустите приложение
python -m uvicorn app.main:app
```

**⚠️ ВАЖНО:**

- Добавьте `secrets/` в `.gitignore`
- Используйте только для development/testing
- НЕ использовать в production

## Secret Management Best Practices

### Генерация HMAC Secret

```bash
# Минимум 32 символа (рекомендуется 64)
openssl rand -hex 32
```

### Генерация JWT Keys

```bash
# Private key (2048-bit RSA)
openssl genrsa -out private_key.pem 2048

# Public key (из private)
openssl rsa -in private_key.pem -pubout -out public_key.pem

# Проверка ключей
openssl rsa -in private_key.pem -noout -text
openssl rsa -pubin -in public_key.pem -noout -text
```

### Ротация Секретов

#### Docker Compose

```bash
# 1. Обновите .env файл
# 2. Recreate контейнер
docker-compose -f docker-compose.secrets.yml up -d --force-recreate admin-module
```

#### Kubernetes

```bash
# 1. Создайте новый Secret
kubectl create secret generic artstore-admin-secrets-v2 \
  --from-literal=SECURITY_AUDIT_HMAC_SECRET='new-secure-secret' \
  --namespace=artstore

# 2. Обновите Deployment
kubectl set env deployment/admin-module \
  --from=secret/artstore-admin-secrets-v2 \
  --namespace=artstore

# 3. Rolling restart (автоматически при изменении Secret reference)
kubectl rollout restart deployment/admin-module -n artstore

# 4. Проверьте статус
kubectl rollout status deployment/admin-module -n artstore
```

### External Secret Management (Production)

Для production рекомендуется использовать:

#### Kubernetes

- **[External Secrets Operator](https://external-secrets.io/)**
  - Sync из AWS Secrets Manager, Azure Key Vault, GCP Secret Manager
  - Automatic rotation support
  - Multi-cloud поддержка

- **[Sealed Secrets](https://github.com/bitnami-labs/sealed-secrets)**
  - Encrypted Secrets в Git
  - GitOps workflow

- **[HashiCorp Vault](https://www.vaultproject.io/)**
  - Centralized secret management
  - Dynamic secrets
  - Audit logging

#### Docker Compose

- **[Docker Secrets](https://docs.docker.com/engine/swarm/secrets/)** (Swarm mode)
- **[Doppler](https://www.doppler.com/)** - Secret management SaaS
- **[Infisical](https://infisical.com/)** - Open-source alternative

## Проверка Configuration

### Verify Secret Loading

```bash
# Docker Compose
docker-compose -f docker-compose.secrets.yml logs admin-module | grep "Secret Provider"

# Kubernetes
kubectl logs -n artstore deployment/admin-module | grep "Secret Provider"
```

**Expected output:**

```
INFO Kubernetes Secret Provider detected and enabled
INFO Environment Variable Secret Provider enabled
INFO Secret Provider chain: KubernetesSecretProvider → EnvSecretProvider
```

### Verify JWT Keys Loading

```bash
# Проверка загрузки ключей
docker-compose -f docker-compose.secrets.yml logs admin-module | grep "JWT"

# Expected:
# INFO JWT private key loaded from direct PEM content
# INFO JWT public key loaded from direct PEM content
# или
# INFO JWT private key loaded from file: /app/keys/private_key.pem
# INFO JWT public key loaded from file: /app/keys/public_key.pem
```

### Health Check

```bash
# Проверка /health/live
curl http://localhost:8000/health/live

# Expected response:
# {"status": "healthy", "timestamp": "2025-11-16T..."}
```

## Troubleshooting

### Secret Not Found

**Проблема:**
```
Secret 'SECURITY_AUDIT_HMAC_SECRET' not found in any provider
```

**Решение:**

1. **Docker Compose**: Проверьте .env файл или environment variables
2. **Kubernetes**: Проверьте что Secret создан и смонтирован
3. **File-based**: Проверьте наличие `./secrets/` директории

```bash
# Kubernetes - проверка Secret
kubectl get secret artstore-admin-secrets -n artstore
kubectl describe secret artstore-admin-secrets -n artstore

# Проверка volume mount в Pod
kubectl exec -n artstore deployment/admin-module -- ls -la /var/run/secrets/artstore
```

### JWT Key Loading Failed

**Проблема:**
```
FileNotFoundError: Private key file not found: /path/to/private_key.pem
```

**Решение:**

1. Проверьте путь к ключам в environment variables
2. Убедитесь что ключи существуют и readable
3. Проверьте volume mounts (Docker Compose или Kubernetes)

```bash
# Docker Compose - проверка volumes
docker-compose -f docker-compose.secrets.yml exec admin-module ls -la /app/keys

# Kubernetes - проверка Secret content
kubectl get secret artstore-admin-secrets -n artstore -o jsonpath='{.data.JWT_PRIVATE_KEY}' | base64 -d
```

### HMAC Secret Too Short

**Проблема:**
```
ValueError: HMAC secret must be at least 32 characters for security
```

**Решение:**

Сгенерируйте новый секрет минимум 32 символа:

```bash
openssl rand -hex 32
```

### Kubernetes Service Account Token Not Found

**Проблема:**
```
Not running in Kubernetes (no service account token)
```

**Это нормально** если приложение НЕ в Kubernetes - fallback на EnvSecretProvider.

Если приложение ДОЛЖНО быть в Kubernetes:

1. Проверьте ServiceAccount в Deployment
2. Проверьте automountServiceAccountToken: true

```yaml
spec:
  serviceAccountName: artstore-admin-sa
  automountServiceAccountToken: true  # По умолчанию true
```

## Мониторинг

### Metrics

```bash
# Prometheus metrics endpoint
curl http://localhost:8000/metrics | grep jwt

# Expected metrics:
# jwt_rotation_total{status="success"} 5
# jwt_active_keys 2
# jwt_key_expiry_hours 23.5
```

### Logs

```bash
# Docker Compose - structured JSON logs
docker-compose -f docker-compose.secrets.yml logs -f admin-module | jq

# Kubernetes - structured JSON logs
kubectl logs -n artstore -f deployment/admin-module | jq
```

## Security Checklist

- [ ] HMAC secret минимум 32 символа (рекомендуется 64)
- [ ] JWT keys сгенерированы с 2048-bit RSA
- [ ] Secrets НЕ закоммичены в Git
- [ ] `.env` файл добавлен в `.gitignore`
- [ ] `secrets/` директория добавлена в `.gitignore`
- [ ] В production используется External Secret Management
- [ ] CORS whitelist настроен (НЕ `["*"]` в production)
- [ ] TLS/HTTPS включен для production endpoints
- [ ] Regular secret rotation schedule настроен
- [ ] Audit logs включены и retention >= 7 лет
- [ ] Prometheus metrics защищены (basic auth или mTLS)

## Support

Для вопросов и issues:
- GitHub Issues: https://github.com/artstore/artstore/issues
- Documentation: https://docs.artstore.local
- Security: security@artstore.local
