#!/bin/bash
#
# ArtStore - Strong Random Password Generator
# Sprint 15 Phase 1.2: Security Hardening Implementation
#
# Генерирует cryptographically secure random passwords для всех компонентов системы.
#
# Usage:
#   ./scripts/generate_secrets.sh [--output-file .env.secrets]
#
# Security Notes:
# - Использует /dev/urandom для cryptographic randomness
# - Passwords включают uppercase, lowercase, digits, special characters
# - Минимальная длина: 24 chars для Grafana, 32 chars для остальных
# - Generated passwords записываются в .env.secrets (НЕ КОММИТИТЬ!)
#

set -euo pipefail

# Colors для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Output file
OUTPUT_FILE="${1:-.env.secrets}"

# Функция генерации strong random password
generate_password() {
    local length=$1
    local charset="A-Za-z0-9!@#$%^&*()-_=+[]{}|;:,.<>?"

    # Используем /dev/urandom для cryptographic randomness
    LC_ALL=C tr -dc "$charset" < /dev/urandom | head -c "$length"
}

# Функция генерации UUID
generate_uuid() {
    if command -v uuidgen &> /dev/null; then
        uuidgen
    else
        # Fallback если uuidgen не установлен
        cat /proc/sys/kernel/random/uuid
    fi
}

echo -e "${YELLOW}=== ArtStore Strong Password Generator ===${NC}"
echo ""
echo "Генерация cryptographically secure random passwords..."
echo ""

# Проверка существования output file
if [ -f "$OUTPUT_FILE" ]; then
    echo -e "${RED}WARNING: $OUTPUT_FILE already exists!${NC}"
    echo -n "Overwrite? (yes/no): "
    read -r confirm
    if [ "$confirm" != "yes" ]; then
        echo "Aborted."
        exit 1
    fi
    echo ""
fi

# Генерация паролей
echo "Generating passwords..."
POSTGRES_PASSWORD=$(generate_password 32)
REDIS_PASSWORD=$(generate_password 32)
GRAFANA_ADMIN_PASSWORD=$(generate_password 24)
MINIO_ROOT_PASSWORD=$(generate_password 32)
MINIO_ROOT_USER=$(generate_password 16)
INITIAL_CLIENT_SECRET=$(generate_password 32)
INITIAL_CLIENT_ID=$(generate_uuid)

# Запись в файл
cat > "$OUTPUT_FILE" << EOF
# =============================================================================
# ArtStore Strong Random Passwords
# Generated: $(date -Iseconds)
# =============================================================================
#
# ⚠️ SECURITY WARNING:
# - НЕ КОММИТЬТЕ этот файл в Git!
# - Добавьте .env.secrets в .gitignore
# - Храните в безопасном месте (password manager, secrets vault)
# - Используйте для production deployment
#
# =============================================================================

# Environment
ENVIRONMENT=production

# PostgreSQL
DB_PASSWORD=$POSTGRES_PASSWORD

# Redis
REDIS_PASSWORD=$REDIS_PASSWORD

# Grafana
GF_SECURITY_ADMIN_PASSWORD=$GRAFANA_ADMIN_PASSWORD

# MinIO
MINIO_ROOT_USER=$MINIO_ROOT_USER
MINIO_ROOT_PASSWORD=$MINIO_ROOT_PASSWORD

# Admin Module - Initial Service Account
INITIAL_CLIENT_ID=$INITIAL_CLIENT_ID
INITIAL_CLIENT_SECRET=$INITIAL_CLIENT_SECRET

# =============================================================================
# Password Strength Summary
# =============================================================================
# PostgreSQL Password:  32 characters (A-Za-z0-9!@#$%^&*()-_=+[]{}|;:,.<>?)
# Redis Password:       32 characters (A-Za-z0-9!@#$%^&*()-_=+[]{}|;:,.<>?)
# Grafana Password:     24 characters (A-Za-z0-9!@#$%^&*()-_=+[]{}|;:,.<>?)
# MinIO User:           16 characters (A-Za-z0-9!@#$%^&*()-_=+[]{}|;:,.<>?)
# MinIO Password:       32 characters (A-Za-z0-9!@#$%^&*()-_=+[]{}|;:,.<>?)
# Client Secret:        32 characters (A-Za-z0-9!@#$%^&*()-_=+[]{}|;:,.<>?)
# =============================================================================

EOF

# Установка безопасных прав доступа
chmod 600 "$OUTPUT_FILE"

echo -e "${GREEN}✓ Passwords generated successfully!${NC}"
echo ""
echo "Output file: $OUTPUT_FILE"
echo "File permissions: 600 (read/write owner only)"
echo ""
echo -e "${YELLOW}Generated credentials summary:${NC}"
echo "  PostgreSQL Password:  32 chars"
echo "  Redis Password:       32 chars"
echo "  Grafana Password:     24 chars"
echo "  MinIO User:           16 chars"
echo "  MinIO Password:       32 chars"
echo "  Initial Client ID:    UUID"
echo "  Initial Client Secret: 32 chars"
echo ""
echo -e "${RED}⚠️ SECURITY REMINDERS:${NC}"
echo "  1. DO NOT commit $OUTPUT_FILE to Git!"
echo "  2. Add $OUTPUT_FILE to .gitignore"
echo "  3. Store credentials in password manager or secrets vault"
echo "  4. Use these credentials for production deployment"
echo "  5. Rotate passwords every 90 days"
echo ""
echo -e "${GREEN}Next steps:${NC}"
echo "  1. Review generated passwords in $OUTPUT_FILE"
echo "  2. Copy to your production .env file OR use as environment variables"
echo "  3. Update docker-compose.yml to use environment variables"
echo "  4. Store $OUTPUT_FILE securely (DO NOT commit!)"
echo ""
echo "Example usage:"
echo "  # Option 1: Use as environment variables"
echo "  export \$(cat $OUTPUT_FILE | xargs)"
echo "  docker-compose up -d"
echo ""
echo "  # Option 2: Copy to production .env"
echo "  cp $OUTPUT_FILE .env.production"
echo "  docker-compose --env-file .env.production up -d"
echo ""
