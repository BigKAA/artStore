#!/bin/bash
# ==============================================================================
# Тест JWT Hot-Reload для Query Module
# ==============================================================================
#
# Проверяет что Query Module автоматически перезагружает публичный ключ
# при изменении файла без перезапуска контейнера.
#
# Использование:
#   ./scripts/test-jwt-hot-reload.sh
#
# Требования:
#   - Docker и docker-compose установлены
#   - Query Module запущен через docker-compose up
#
# ==============================================================================

set -e  # Exit on error

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Константы
CONTAINER_NAME="artstore_query_module"
KEY_FILE="./query-module/keys/public_key.pem"
BACKUP_KEY_FILE="./query-module/keys/public_key.pem.backup"
TEST_KEY_FILE="./query-module/keys/public_key_test.pem"

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}JWT Hot-Reload Test для Query Module${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# Шаг 1: Проверка что контейнер запущен
echo -e "${YELLOW}[1/6]${NC} Проверка что Query Module запущен..."
if ! docker ps | grep -q "$CONTAINER_NAME"; then
    echo -e "${RED}✗ ОШИБКА: Контейнер $CONTAINER_NAME не запущен${NC}"
    echo -e "Запустите: docker-compose up -d query-module"
    exit 1
fi
echo -e "${GREEN}✓ Query Module запущен${NC}"
echo ""

# Шаг 2: Создание backup оригинального ключа
echo -e "${YELLOW}[2/6]${NC} Создание backup оригинального ключа..."
if [ ! -f "$KEY_FILE" ]; then
    echo -e "${RED}✗ ОШИБКА: Файл ключа не найден: $KEY_FILE${NC}"
    exit 1
fi
cp "$KEY_FILE" "$BACKUP_KEY_FILE"
echo -e "${GREEN}✓ Backup создан: $BACKUP_KEY_FILE${NC}"
echo ""

# Шаг 3: Создание тестового ключа (fake для проверки hot-reload)
echo -e "${YELLOW}[3/6]${NC} Создание тестового ключа..."
cat > "$TEST_KEY_FILE" <<EOF
-----BEGIN PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAyKz8vPHqkuFXBPPqS0T7
testkey123456789testkey123456789testkey123456789testkey123456789
testkey123456789testkey123456789testkey123456789testkey123456789
testkey123456789testkey123456789testkey123456789testkey123456789
testkey123456789testkey123456789testkey123456789testkey123456789
testkey123456789testkey123456789testkey123456789testkey123456789
-----END PUBLIC KEY-----
EOF
echo -e "${GREEN}✓ Тестовый ключ создан${NC}"
echo ""

# Шаг 4: Замена ключа (симуляция cert-manager rotation)
echo -e "${YELLOW}[4/6]${NC} Замена ключа на тестовый (симуляция cert-manager rotation)..."
cp "$TEST_KEY_FILE" "$KEY_FILE"
echo -e "${GREEN}✓ Ключ заменен${NC}"
echo ""

# Шаг 5: Ожидание hot-reload (watchfiles обычно срабатывает за 1-2 секунды)
echo -e "${YELLOW}[5/6]${NC} Ожидание hot-reload (3 секунды)..."
sleep 3
echo -e "${GREEN}✓ Ожидание завершено${NC}"
echo ""

# Шаг 6: Проверка логов на наличие hot-reload события
echo -e "${YELLOW}[6/6]${NC} Проверка логов Query Module на hot-reload событие..."
echo ""
echo -e "${BLUE}=== Последние 20 строк логов ===${NC}"
docker logs --tail 20 "$CONTAINER_NAME"
echo ""

# Проверка наличия успешного hot-reload сообщения
if docker logs --tail 50 "$CONTAINER_NAME" | grep -q "JWT key file changed\|JWT public key reloaded successfully"; then
    echo -e "${GREEN}✓ SUCCESS: Hot-reload сработал!${NC}"
    echo -e "${GREEN}  Найдено сообщение о перезагрузке ключа в логах${NC}"
    TEST_RESULT="SUCCESS"
else
    echo -e "${RED}✗ WARNING: Hot-reload сообщение НЕ найдено в логах${NC}"
    echo -e "${YELLOW}  Это может означать:${NC}"
    echo -e "${YELLOW}  - Watcher еще не успел среагировать (попробуйте подождать еще)${NC}"
    echo -e "${YELLOW}  - Проблема с инициализацией JWTKeyManager${NC}"
    TEST_RESULT="FAILED"
fi
echo ""

# Восстановление оригинального ключа
echo -e "${YELLOW}Восстановление оригинального ключа...${NC}"
cp "$BACKUP_KEY_FILE" "$KEY_FILE"
rm -f "$BACKUP_KEY_FILE" "$TEST_KEY_FILE"
echo -e "${GREEN}✓ Оригинальный ключ восстановлен${NC}"
echo ""

# Итоговый результат
echo -e "${BLUE}========================================${NC}"
if [ "$TEST_RESULT" = "SUCCESS" ]; then
    echo -e "${GREEN}✓ ТЕСТ ПРОЙДЕН: JWT Hot-Reload работает!${NC}"
    echo -e "${BLUE}========================================${NC}"
    exit 0
else
    echo -e "${RED}✗ ТЕСТ НЕ ПРОЙДЕН: Проверьте логи выше${NC}"
    echo -e "${BLUE}========================================${NC}"
    exit 1
fi
