#!/bin/bash

################################################################################
# ArtStore TLS 1.3 + mTLS Certificate Generation Script
# Sprint 16 Phase 4 - Security Hardening
#
# Генерирует:
# 1. Certificate Authority (CA) для подписи server и client certificates
# 2. Server certificates для всех 4 модулей (admin, storage, ingester, query)
# 3. Client certificates для mTLS inter-service communication
#
# Использование:
#   ./generate-certs.sh [environment]
#   environment: development (default) | production
#
# Development Mode:
#   - Self-signed certificates со сроком действия 365 дней
#   - localhost + 127.0.0.1 в SAN
#   - Подходит для локальной разработки и тестирования
#
# Production Mode:
#   - Certificates для production deployment
#   - Реальные доменные имена (требуют DNS configuration)
#   - Рекомендуется использовать Let's Encrypt для production
#
# ВАЖНО: Для production используйте Let's Encrypt или корпоративный CA!
################################################################################

set -euo pipefail

# Цветной вывод
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Константы
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CA_DIR="${SCRIPT_DIR}/ca"
SERVER_CERTS_DIR="${SCRIPT_DIR}/server-certs"
CLIENT_CERTS_DIR="${SCRIPT_DIR}/client-certs"

# Environment (development или production)
ENVIRONMENT="${1:-development}"

# Валидность сертификатов (в днях)
if [ "$ENVIRONMENT" = "production" ]; then
    VALIDITY_DAYS=90  # Production: 90 дней (NIST recommendation)
else
    VALIDITY_DAYS=365  # Development: 1 год
fi

# OpenSSL configuration paths
CA_CONFIG="${CA_DIR}/ca-openssl.cnf"

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}ArtStore TLS Certificate Generation${NC}"
echo -e "${GREEN}Environment: ${ENVIRONMENT}${NC}"
echo -e "${GREEN}Validity: ${VALIDITY_DAYS} days${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

################################################################################
# Функция: Генерация CA (Certificate Authority)
################################################################################
generate_ca() {
    echo -e "${YELLOW}[1/3] Генерация Certificate Authority (CA)...${NC}"

    # Создаем OpenSSL config для CA
    cat > "${CA_CONFIG}" <<EOF
[ ca ]
default_ca = CA_default

[ CA_default ]
dir              = ${CA_DIR}
certs            = \$dir/certs
crl_dir          = \$dir/crl
new_certs_dir    = \$dir/newcerts
database         = \$dir/index.txt
serial           = \$dir/serial
RANDFILE         = \$dir/.rand

private_key      = \$dir/ca-key.pem
certificate      = \$dir/ca-cert.pem

crlnumber        = \$dir/crlnumber
crl              = \$dir/crl.pem
crl_extensions   = crl_ext
default_crl_days = 30

default_md       = sha256
preserve         = no
policy           = policy_loose

[ policy_loose ]
countryName             = optional
stateOrProvinceName     = optional
localityName            = optional
organizationName        = optional
organizationalUnitName  = optional
commonName              = supplied
emailAddress            = optional

[ req ]
default_bits        = 4096
distinguished_name  = req_distinguished_name
string_mask         = utf8only
default_md          = sha256
x509_extensions     = v3_ca

[ req_distinguished_name ]
countryName                     = Country Name (2 letter code)
stateOrProvinceName             = State or Province Name
localityName                    = Locality Name
0.organizationName              = Organization Name
organizationalUnitName          = Organizational Unit Name
commonName                      = Common Name
emailAddress                    = Email Address

[ v3_ca ]
subjectKeyIdentifier = hash
authorityKeyIdentifier = keyid:always,issuer
basicConstraints = critical, CA:true
keyUsage = critical, digitalSignature, cRLSign, keyCertSign

[ v3_intermediate_ca ]
subjectKeyIdentifier = hash
authorityKeyIdentifier = keyid:always,issuer
basicConstraints = critical, CA:true, pathlen:0
keyUsage = critical, digitalSignature, cRLSign, keyCertSign

[ usr_cert ]
basicConstraints = CA:FALSE
nsCertType = client, email
nsComment = "OpenSSL Generated Client Certificate"
subjectKeyIdentifier = hash
authorityKeyIdentifier = keyid,issuer
keyUsage = critical, nonRepudiation, digitalSignature, keyEncipherment
extendedKeyUsage = clientAuth, emailProtection

[ server_cert ]
basicConstraints = CA:FALSE
nsCertType = server
nsComment = "OpenSSL Generated Server Certificate"
subjectKeyIdentifier = hash
authorityKeyIdentifier = keyid,issuer:always
keyUsage = critical, digitalSignature, keyEncipherment
extendedKeyUsage = serverAuth

[ crl_ext ]
authorityKeyIdentifier=keyid:always

[ ocsp ]
basicConstraints = CA:FALSE
subjectKeyIdentifier = hash
authorityKeyIdentifier = keyid,issuer
keyUsage = critical, digitalSignature
extendedKeyUsage = critical, OCSPSigning
EOF

    # Создаем необходимые директории и файлы
    mkdir -p "${CA_DIR}"/{certs,crl,newcerts}
    touch "${CA_DIR}/index.txt"
    echo 1000 > "${CA_DIR}/serial"

    # Генерируем CA private key (4096 бит для максимальной безопасности)
    if [ ! -f "${CA_DIR}/ca-key.pem" ]; then
        openssl genpkey \
            -algorithm RSA \
            -pkeyopt rsa_keygen_bits:4096 \
            -out "${CA_DIR}/ca-key.pem"

        chmod 400 "${CA_DIR}/ca-key.pem"
        echo -e "${GREEN}✓ CA private key generated${NC}"
    else
        echo -e "${YELLOW}⚠ CA private key already exists, skipping...${NC}"
    fi

    # Генерируем CA certificate (self-signed)
    if [ ! -f "${CA_DIR}/ca-cert.pem" ]; then
        openssl req -config "${CA_CONFIG}" \
            -key "${CA_DIR}/ca-key.pem" \
            -new -x509 -days $((VALIDITY_DAYS * 10)) -sha256 \
            -extensions v3_ca \
            -out "${CA_DIR}/ca-cert.pem" \
            -subj "/C=RU/ST=Moscow/L=Moscow/O=ArtStore/OU=Infrastructure/CN=ArtStore Root CA"

        echo -e "${GREEN}✓ CA certificate generated (valid for $((VALIDITY_DAYS * 10)) days)${NC}"
    else
        echo -e "${YELLOW}⚠ CA certificate already exists, skipping...${NC}"
    fi

    echo ""
}

################################################################################
# Функция: Генерация Server Certificate для модуля
################################################################################
generate_server_cert() {
    local module_name="$1"
    local common_name="$2"
    local san_names="$3"

    echo -e "${YELLOW}Генерация server certificate для ${module_name}...${NC}"

    local cert_dir="${SERVER_CERTS_DIR}/${module_name}"
    mkdir -p "${cert_dir}"

    # Генерируем private key
    openssl genpkey \
        -algorithm RSA \
        -pkeyopt rsa_keygen_bits:2048 \
        -out "${cert_dir}/server-key.pem"

    chmod 400 "${cert_dir}/server-key.pem"

    # Создаем OpenSSL config для этого сертификата с SAN
    cat > "${cert_dir}/server-openssl.cnf" <<EOF
[ req ]
default_bits        = 2048
distinguished_name  = req_distinguished_name
req_extensions      = req_ext
string_mask         = utf8only
default_md          = sha256

[ req_distinguished_name ]
countryName                     = Country Name (2 letter code)
stateOrProvinceName             = State or Province Name
localityName                    = Locality Name
0.organizationName              = Organization Name
organizationalUnitName          = Organizational Unit Name
commonName                      = Common Name

[ req_ext ]
subjectAltName = @alt_names

[ alt_names ]
${san_names}

[ server_cert ]
basicConstraints = CA:FALSE
nsCertType = server
nsComment = "OpenSSL Generated Server Certificate"
subjectKeyIdentifier = hash
authorityKeyIdentifier = keyid,issuer:always
keyUsage = critical, digitalSignature, keyEncipherment
extendedKeyUsage = serverAuth
subjectAltName = @alt_names
EOF

    # Генерируем CSR (Certificate Signing Request)
    openssl req -config "${cert_dir}/server-openssl.cnf" \
        -key "${cert_dir}/server-key.pem" \
        -new -sha256 \
        -out "${cert_dir}/server-csr.pem" \
        -subj "/C=RU/ST=Moscow/L=Moscow/O=ArtStore/OU=${module_name}/CN=${common_name}"

    # Подписываем CSR нашим CA
    openssl x509 -req \
        -in "${cert_dir}/server-csr.pem" \
        -CA "${CA_DIR}/ca-cert.pem" \
        -CAkey "${CA_DIR}/ca-key.pem" \
        -CAcreateserial \
        -out "${cert_dir}/server-cert.pem" \
        -days "${VALIDITY_DAYS}" \
        -sha256 \
        -extfile "${cert_dir}/server-openssl.cnf" \
        -extensions server_cert

    # Создаем fullchain (server cert + CA cert) для некоторых приложений
    cat "${cert_dir}/server-cert.pem" "${CA_DIR}/ca-cert.pem" > "${cert_dir}/server-fullchain.pem"

    echo -e "${GREEN}✓ Server certificate для ${module_name} готов${NC}"
    echo "  - Certificate: ${cert_dir}/server-cert.pem"
    echo "  - Private Key: ${cert_dir}/server-key.pem"
    echo "  - Fullchain: ${cert_dir}/server-fullchain.pem"
    echo ""
}

################################################################################
# Функция: Генерация Client Certificate для mTLS
################################################################################
generate_client_cert() {
    local client_name="$1"

    echo -e "${YELLOW}Генерация client certificate для ${client_name}...${NC}"

    # Генерируем private key
    openssl genpkey \
        -algorithm RSA \
        -pkeyopt rsa_keygen_bits:2048 \
        -out "${CLIENT_CERTS_DIR}/${client_name}-key.pem"

    chmod 400 "${CLIENT_CERTS_DIR}/${client_name}-key.pem"

    # Генерируем CSR
    openssl req -new \
        -key "${CLIENT_CERTS_DIR}/${client_name}-key.pem" \
        -out "${CLIENT_CERTS_DIR}/${client_name}-csr.pem" \
        -subj "/C=RU/ST=Moscow/L=Moscow/O=ArtStore/OU=Services/CN=${client_name}"

    # Подписываем CSR нашим CA
    openssl x509 -req \
        -in "${CLIENT_CERTS_DIR}/${client_name}-csr.pem" \
        -CA "${CA_DIR}/ca-cert.pem" \
        -CAkey "${CA_DIR}/ca-key.pem" \
        -CAcreateserial \
        -out "${CLIENT_CERTS_DIR}/${client_name}-cert.pem" \
        -days "${VALIDITY_DAYS}" \
        -sha256 \
        -extfile "${CA_CONFIG}" \
        -extensions usr_cert

    echo -e "${GREEN}✓ Client certificate для ${client_name} готов${NC}"
    echo "  - Certificate: ${CLIENT_CERTS_DIR}/${client_name}-cert.pem"
    echo "  - Private Key: ${CLIENT_CERTS_DIR}/${client_name}-key.pem"
    echo ""
}

################################################################################
# Главная логика
################################################################################
main() {
    # 1. Генерируем CA
    generate_ca

    # 2. Генерируем Server Certificates для всех модулей
    echo -e "${YELLOW}[2/3] Генерация Server Certificates...${NC}"

    if [ "$ENVIRONMENT" = "production" ]; then
        # Production: используем реальные доменные имена
        echo -e "${RED}ПРЕДУПРЕЖДЕНИЕ: Production режим требует настройки DNS!${NC}"
        echo -e "${YELLOW}Укажите реальные доменные имена или используйте Let's Encrypt${NC}"
        echo ""

        generate_server_cert "admin-module" "admin.artstore.local" \
            "DNS.1 = admin.artstore.local\nDNS.2 = admin-module"

        generate_server_cert "storage-element" "storage.artstore.local" \
            "DNS.1 = storage.artstore.local\nDNS.2 = storage-element"

        generate_server_cert "ingester-module" "ingester.artstore.local" \
            "DNS.1 = ingester.artstore.local\nDNS.2 = ingester-module"

        generate_server_cert "query-module" "query.artstore.local" \
            "DNS.1 = query.artstore.local\nDNS.2 = query-module"
    else
        # Development: localhost + Docker service names
        generate_server_cert "admin-module" "localhost" \
            "DNS.1 = localhost\nDNS.2 = admin-module\nIP.1 = 127.0.0.1"

        generate_server_cert "storage-element" "localhost" \
            "DNS.1 = localhost\nDNS.2 = storage-element\nIP.1 = 127.0.0.1"

        generate_server_cert "ingester-module" "localhost" \
            "DNS.1 = localhost\nDNS.2 = ingester-module\nIP.1 = 127.0.0.1"

        generate_server_cert "query-module" "localhost" \
            "DNS.1 = localhost\nDNS.2 = query-module\nIP.1 = 127.0.0.1"
    fi

    # 3. Генерируем Client Certificates для mTLS
    echo -e "${YELLOW}[3/3] Генерация Client Certificates для mTLS...${NC}"

    generate_client_cert "ingester-client"
    generate_client_cert "query-client"
    generate_client_cert "admin-client"

    # Финальный summary
    echo -e "${GREEN}========================================${NC}"
    echo -e "${GREEN}Certificate Generation Complete!${NC}"
    echo -e "${GREEN}========================================${NC}"
    echo ""
    echo -e "${YELLOW}Summary:${NC}"
    echo "  - CA Certificate: ${CA_DIR}/ca-cert.pem"
    echo "  - Server Certificates: ${SERVER_CERTS_DIR}/"
    echo "  - Client Certificates: ${CLIENT_CERTS_DIR}/"
    echo ""
    echo -e "${YELLOW}Next Steps:${NC}"
    echo "  1. Скопируйте CA certificate в trust store всех модулей"
    echo "  2. Настройте TLS в config.py каждого модуля"
    echo "  3. Обновите docker-compose.yml с volume mounts для certificates"
    echo "  4. Включите TLS через environment variables: TLS_ENABLED=true"
    echo ""

    if [ "$ENVIRONMENT" = "production" ]; then
        echo -e "${RED}ВАЖНО: Для production используйте Let's Encrypt!${NC}"
        echo "  - Автоматическое обновление certificates"
        echo "  - Доверенные публичные CA"
        echo "  - Инструкция: admin-module/deployment-examples/tls-certificates-README.md"
        echo ""
    fi

    echo -e "${YELLOW}Проверка сертификатов:${NC}"
    echo "  # CA certificate:"
    echo "  openssl x509 -in ${CA_DIR}/ca-cert.pem -text -noout"
    echo ""
    echo "  # Server certificate (admin-module):"
    echo "  openssl x509 -in ${SERVER_CERTS_DIR}/admin-module/server-cert.pem -text -noout"
    echo ""
    echo "  # Verify chain:"
    echo "  openssl verify -CAfile ${CA_DIR}/ca-cert.pem ${SERVER_CERTS_DIR}/admin-module/server-cert.pem"
    echo ""
}

# Запуск
main
