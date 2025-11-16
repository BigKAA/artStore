# ArtStore TLS 1.3 + mTLS Infrastructure

**Sprint 16 Phase 4 - Security Hardening**

Эта директория содержит инфраструктуру для TLS 1.3 транспортного шифрования и mTLS (Mutual TLS) межсервисной аутентификации.

---

## 📋 Содержание

1. [Обзор](#обзор)
2. [Структура директории](#структура-директории)
3. [Quick Start](#quick-start)
4. [Certificate Generation](#certificate-generation)
5. [Configuration](#configuration)
6. [Production Deployment](#production-deployment)
7. [Troubleshooting](#troubleshooting)
8. [Security Best Practices](#security-best-practices)

---

## Обзор

### TLS 1.3 Features

- **Транспортное шифрование**: Все HTTP соединения защищены TLS 1.3
- **Perfect Forward Secrecy (PFS)**: Эфемерные ключи для каждой сессии
- **AEAD Cipher Suites**: Только authenticated encryption (AES-GCM, ChaCha20-Poly1305)
- **0-RTT Resumption**: Быстрое восстановление TLS сессий (опционально)

### mTLS (Mutual TLS) Features

- **Client Authentication**: Взаимная аутентификация сервера и клиента
- **Certificate-Based Auth**: Service-to-service auth через client certificates
- **CN Whitelist**: Валидация Common Name для trusted services
- **Certificate Rotation**: Автоматическое обновление certificates каждые 90 дней

---

## Структура директории

```
tls-infrastructure/
├── README.md                           # Этот файл
├── generate-certs.sh                   # Скрипт генерации certificates
│
├── ca/                                 # Certificate Authority
│   ├── ca-cert.pem                     # CA certificate (публичный)
│   ├── ca-key.pem                      # CA private key (секретный!)
│   └── ca-openssl.cnf                  # OpenSSL config для CA
│
├── server-certs/                       # Server certificates
│   ├── admin-module/
│   │   ├── server-cert.pem             # Server certificate
│   │   ├── server-key.pem              # Server private key
│   │   ├── server-fullchain.pem        # Cert + CA chain
│   │   └── server-openssl.cnf          # OpenSSL config
│   ├── storage-element/
│   ├── ingester-module/
│   └── query-module/
│
└── client-certs/                       # Client certificates для mTLS
    ├── ingester-client-cert.pem        # Ingester → Storage mTLS
    ├── ingester-client-key.pem
    ├── query-client-cert.pem           # Query → Storage mTLS
    ├── query-client-key.pem
    ├── admin-client-cert.pem           # Admin → * mTLS
    └── admin-client-key.pem
```

---

## Quick Start

### 1. Генерация Development Certificates

```bash
cd admin-module/tls-infrastructure
./generate-certs.sh development
```

Это создаст:
- ✅ Self-signed CA certificate
- ✅ Server certificates для всех 4 модулей (localhost + Docker service names)
- ✅ Client certificates для mTLS inter-service communication
- ✅ Срок действия: 365 дней

### 2. Проверка сгенерированных certificates

```bash
# Проверить CA certificate
openssl x509 -in ca/ca-cert.pem -text -noout | grep -E "Issuer|Subject|Not"

# Проверить server certificate
openssl x509 -in server-certs/admin-module/server-cert.pem -text -noout | grep -E "CN=|DNS:|IP:"

# Проверить chain validation
openssl verify -CAfile ca/ca-cert.pem server-certs/admin-module/server-cert.pem
# Expected: server-certs/admin-module/server-cert.pem: OK
```

### 3. Включение TLS в модулях

Обновите `.env` файл каждого модуля:

```bash
# TLS Configuration
TLS_ENABLED=true
TLS_CERT_FILE=/app/tls/server-cert.pem
TLS_KEY_FILE=/app/tls/server-key.pem
TLS_CA_CERT_FILE=/app/tls/ca-cert.pem
TLS_PROTOCOL_VERSION=TLSv1.3
TLS_VERIFY_MODE=CERT_REQUIRED  # Для mTLS
```

### 4. Docker Compose Configuration

См. `admin-module/deployment-examples/docker-compose.tls.yml` для полного примера.

---

## Certificate Generation

### Development Mode (Default)

```bash
./generate-certs.sh development
```

**Features**:
- Self-signed certificates
- 365 дней validity
- SAN: `localhost`, `127.0.0.1`, Docker service names
- Подходит для локальной разработки и тестирования

### Production Mode

```bash
./generate-certs.sh production
```

**Features**:
- 90 дней validity (NIST recommendation)
- SAN: Реальные доменные имена (требуют DNS setup)
- **ВАЖНО**: Для production рекомендуется Let's Encrypt!

### Manual Certificate Generation

Если нужна кастомная конфигурация:

```bash
# 1. Создать CA
openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:4096 -out ca/ca-key.pem
openssl req -new -x509 -days 3650 -key ca/ca-key.pem -out ca/ca-cert.pem \
    -subj "/C=RU/ST=Moscow/L=Moscow/O=ArtStore/CN=ArtStore Root CA"

# 2. Создать server key и CSR
openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:2048 -out server-key.pem
openssl req -new -key server-key.pem -out server-csr.pem \
    -subj "/C=RU/ST=Moscow/L=Moscow/O=ArtStore/CN=admin-module"

# 3. Подписать CSR с помощью CA
openssl x509 -req -in server-csr.pem -CA ca/ca-cert.pem -CAkey ca/ca-key.pem \
    -CAcreateserial -out server-cert.pem -days 365 -sha256
```

---

## Configuration

### TLS Settings (app/core/config.py)

Все модули используют unified TLS configuration:

```python
from pydantic import BaseSettings, Field

class TLSSettings(BaseSettings):
    """TLS 1.3 configuration settings.

    Sprint 16 Phase 4: TLS 1.3 + mTLS Infrastructure
    """
    model_config = SettingsConfigDict(
        env_prefix="TLS_",
        case_sensitive=False
    )

    enabled: bool = Field(
        default=False,
        alias="enabled",
        description="Enable TLS 1.3 encryption"
    )

    cert_file: str = Field(
        default="",
        alias="cert_file",
        description="Path to server certificate file"
    )

    key_file: str = Field(
        default="",
        alias="key_file",
        description="Path to server private key file"
    )

    ca_cert_file: str = Field(
        default="",
        alias="ca_cert_file",
        description="Path to CA certificate for client validation (mTLS)"
    )

    protocol_version: str = Field(
        default="TLSv1.3",
        alias="protocol_version",
        description="Minimum TLS protocol version"
    )

    ciphers: str = Field(
        default="TLS_AES_256_GCM_SHA384:TLS_CHACHA20_POLY1305_SHA256:TLS_AES_128_GCM_SHA256",
        alias="ciphers",
        description="Allowed cipher suites (AEAD only)"
    )

    verify_mode: str = Field(
        default="CERT_OPTIONAL",
        alias="verify_mode",
        description="Certificate verification mode: CERT_NONE, CERT_OPTIONAL, CERT_REQUIRED"
    )
```

### Environment Variables

```bash
# Basic TLS
TLS_ENABLED=true
TLS_CERT_FILE=/path/to/server-cert.pem
TLS_KEY_FILE=/path/to/server-key.pem
TLS_PROTOCOL_VERSION=TLSv1.3

# mTLS (Mutual TLS)
TLS_CA_CERT_FILE=/path/to/ca-cert.pem
TLS_VERIFY_MODE=CERT_REQUIRED  # Enforce client certificates

# Advanced
TLS_CIPHERS="TLS_AES_256_GCM_SHA384:TLS_CHACHA20_POLY1305_SHA256"
```

### Uvicorn SSL Context

В `app/main.py`:

```python
import ssl
from app.core.config import settings

if settings.tls.enabled:
    ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ssl_context.minimum_version = ssl.TLSVersion.TLSv1_3

    # Load server certificate and key
    ssl_context.load_cert_chain(
        certfile=settings.tls.cert_file,
        keyfile=settings.tls.key_file
    )

    # mTLS: Load CA for client validation
    if settings.tls.verify_mode == "CERT_REQUIRED":
        ssl_context.load_verify_locations(cafile=settings.tls.ca_cert_file)
        ssl_context.verify_mode = ssl.CERT_REQUIRED

    # Set cipher suites
    ssl_context.set_ciphers(settings.tls.ciphers)

    # Run with SSL
    uvicorn.run(app, host="0.0.0.0", port=8000, ssl=ssl_context)
else:
    uvicorn.run(app, host="0.0.0.0", port=8000)
```

---

## Production Deployment

### ⚠️ ВАЖНО: Let's Encrypt для Production

Для production НЕ используйте self-signed certificates! Используйте Let's Encrypt:

#### Option 1: Certbot (Recommended)

```bash
# Install certbot
sudo apt-get install certbot

# Generate certificates
sudo certbot certonly --standalone -d admin.artstore.com

# Certificates location
/etc/letsencrypt/live/admin.artstore.com/fullchain.pem  # Certificate
/etc/letsencrypt/live/admin.artstore.com/privkey.pem    # Private key

# Auto-renewal (cron job)
0 0 * * * certbot renew --quiet --post-hook "systemctl reload artstore-admin"
```

#### Option 2: ACME.sh

```bash
# Install acme.sh
curl https://get.acme.sh | sh

# Generate certificates
acme.sh --issue -d admin.artstore.com --standalone

# Install certificates
acme.sh --install-cert -d admin.artstore.com \
    --cert-file /opt/artstore/tls/server-cert.pem \
    --key-file /opt/artstore/tls/server-key.pem \
    --fullchain-file /opt/artstore/tls/server-fullchain.pem \
    --reloadcmd "systemctl reload artstore-admin"
```

#### Option 3: Kubernetes Cert-Manager

```yaml
apiVersion: cert-manager.io/v1
kind: Certificate
metadata:
  name: artstore-admin-tls
  namespace: artstore
spec:
  secretName: artstore-admin-tls
  issuerRef:
    name: letsencrypt-prod
    kind: ClusterIssuer
  dnsNames:
    - admin.artstore.com
```

### Certificate Rotation

#### Automated Rotation (Recommended)

```bash
# Cron job для проверки expiration
0 0 * * * /opt/artstore/scripts/check-cert-expiry.sh

# check-cert-expiry.sh
#!/bin/bash
CERT_FILE="/opt/artstore/tls/server-cert.pem"
DAYS_UNTIL_EXPIRY=$(openssl x509 -in "$CERT_FILE" -noout -enddate | \
    awk -F= '{print $2}' | xargs -I {} date -d {} +%s | \
    awk -v now="$(date +%s)" '{print int(($1 - now) / 86400)}')

if [ "$DAYS_UNTIL_EXPIRY" -lt 30 ]; then
    echo "Certificate expires in $DAYS_UNTIL_EXPIRY days, renewing..."
    certbot renew --force-renewal
    systemctl reload artstore-*
fi
```

#### Manual Rotation

```bash
# 1. Generate new certificates
cd admin-module/tls-infrastructure
./generate-certs.sh production

# 2. Update Docker Compose volume mounts
# 3. Restart services
docker-compose restart admin-module storage-element ingester-module query-module
```

---

## Troubleshooting

### Problem: "SSL: CERTIFICATE_VERIFY_FAILED"

**Причина**: CA certificate не добавлен в trust store

**Решение**:
```bash
# Option 1: Update TLS_CA_CERT_FILE environment variable
export TLS_CA_CERT_FILE=/path/to/ca-cert.pem

# Option 2: Add CA to system trust store (Linux)
sudo cp ca/ca-cert.pem /usr/local/share/ca-certificates/artstore-ca.crt
sudo update-ca-certificates

# Option 3: Disable verification (НЕ для production!)
export TLS_VERIFY_MODE=CERT_NONE
```

### Problem: "SSL: WRONG_VERSION_NUMBER"

**Причина**: Client подключается по HTTP вместо HTTPS

**Решение**:
```bash
# Проверить URL
curl https://localhost:8000/health/live  # ✅ HTTPS
curl http://localhost:8000/health/live   # ❌ HTTP (ошибка)
```

### Problem: "Certificate has expired"

**Проверка expiration date**:
```bash
openssl x509 -in server-cert.pem -noout -enddate
# Expected: notAfter=Feb 16 12:00:00 2026 GMT
```

**Решение**: Regenerate certificates
```bash
./generate-certs.sh development
```

### Problem: "Hostname mismatch"

**Причина**: SAN (Subject Alternative Name) не соответствует подключаемому hostname

**Проверка SAN**:
```bash
openssl x509 -in server-cert.pem -text -noout | grep -A1 "Subject Alternative Name"
# Expected: DNS:localhost, DNS:admin-module, IP Address:127.0.0.1
```

**Решение**: Regenerate certificate с правильными SAN entries

---

## Security Best Practices

### ✅ DO

1. **Use Let's Encrypt для production** - Автоматическое обновление, публичное доверие
2. **Rotate certificates каждые 90 дней** - NIST recommendation
3. **Use TLS 1.3 only** - Отключить TLS 1.2 и ниже
4. **Enable Perfect Forward Secrecy** - Эфемерные ключи (ECDHE)
5. **Use AEAD cipher suites only** - AES-GCM, ChaCha20-Poly1305
6. **Enable mTLS для inter-service** - Mutual authentication
7. **Restrict key permissions** - `chmod 400` для private keys
8. **Monitor certificate expiration** - Alerts за 30 дней
9. **Use strong key sizes** - RSA 2048+ или ECDSA 256+
10. **Validate certificate chains** - Проверять CA signature

### ❌ DON'T

1. **Don't use self-signed в production** - Только Let's Encrypt или корпоративный CA
2. **Don't commit private keys** - `.gitignore` для `*.pem`, `*.key`
3. **Don't use weak ciphers** - Отключить CBC, RC4, 3DES
4. **Don't allow TLS 1.0/1.1** - Minimum TLS 1.2, prefer 1.3
5. **Don't share private keys** - Each service = unique keypair
6. **Don't skip certificate validation** - `CERT_REQUIRED` для production
7. **Don't use MD5/SHA1** - Только SHA256+
8. **Don't ignore expiration warnings** - Automate renewal
9. **Don't expose private keys** - Restrict file permissions
10. **Don't use insecure key generation** - Use `openssl genpkey`, not `genrsa`

---

## References

- **NIST SP 800-52 Rev. 2**: Guidelines for TLS Implementations
- **RFC 8446**: The Transport Layer Security (TLS) Protocol Version 1.3
- **Mozilla SSL Configuration Generator**: https://ssl-config.mozilla.org/
- **Let's Encrypt Documentation**: https://letsencrypt.org/docs/
- **OpenSSL Documentation**: https://www.openssl.org/docs/

---

**Next Steps**: См. `admin-module/deployment-examples/docker-compose.tls.yml` для примеров deployment с TLS/mTLS.
