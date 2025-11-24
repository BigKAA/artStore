#!/bin/bash
set -e

# Скрипт для тестирования Storage Element с LOCAL backend в режиме EDIT
# Автор: Claude Code
# Дата: 2025-11-24

# Цвета для вывода
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Счетчики тестов
TOTAL_TESTS=0
PASSED_TESTS=0
FAILED_TESTS=0

# Функция для вывода результата теста
test_result() {
  local test_name="$1"
  local status="$2"
  local message="$3"

  TOTAL_TESTS=$((TOTAL_TESTS + 1))

  if [ "$status" == "PASS" ]; then
    echo -e "${GREEN}[✓] $test_name${NC}"
    [ -n "$message" ] && echo -e "    ${BLUE}$message${NC}"
    PASSED_TESTS=$((PASSED_TESTS + 1))
  else
    echo -e "${RED}[✗] $test_name${NC}"
    [ -n "$message" ] && echo -e "    ${RED}$message${NC}"
    FAILED_TESTS=$((FAILED_TESTS + 1))
  fi
}

echo -e "${YELLOW}========================================${NC}"
echo -e "${YELLOW}Storage Element LOCAL Backend Testing${NC}"
echo -e "${YELLOW}========================================${NC}"
echo

# Конфигурация
BASE_URL="http://localhost:8010"
ADMIN_URL="http://localhost:8000"
CLIENT_ID="admin-service"
CLIENT_SECRET="change_this_in_production"
AUTH_ENDPOINT="/api/v1/auth/token"

# Временные файлы
TEST_FILE="/tmp/test_local_$(date +%s).txt"
DOWNLOADED_FILE="/tmp/downloaded_local_$(date +%s).txt"
LARGE_FILE="/tmp/large_local_$(date +%s).bin"

# Создать тестовый файл
echo "This is a test document for LOCAL storage backend" > "$TEST_FILE"
echo "Created at: $(date)" >> "$TEST_FILE"
echo "Test ID: $(date +%s)_$$" >> "$TEST_FILE"

# === ЭТАП 1: Получение JWT токена ===
echo -e "${YELLOW}[ЭТАП 1] Получение JWT токена...${NC}"
TOKEN_RESPONSE=$(curl -s -X POST "$ADMIN_URL$AUTH_ENDPOINT" \
  -H "Content-Type: application/json" \
  -d "{
    \"client_id\": \"$CLIENT_ID\",
    \"client_secret\": \"$CLIENT_SECRET\"
  }")

TOKEN=$(echo "$TOKEN_RESPONSE" | jq -r '.access_token')

if [ -z "$TOKEN" ] || [ "$TOKEN" == "null" ]; then
  test_result "Получение JWT токена" "FAIL" "Не удалось получить токен"
  echo -e "${RED}Response: $TOKEN_RESPONSE${NC}"
  exit 1
fi
test_result "Получение JWT токена" "PASS" "Токен получен успешно"
echo

# === ЭТАП 2: Health Checks ===
echo -e "${YELLOW}[ЭТАП 2] Проверка health checks...${NC}"

LIVE_RESPONSE=$(curl -s "$BASE_URL/health/live")
LIVE_STATUS=$(echo "$LIVE_RESPONSE" | jq -r '.status')
if [ "$LIVE_STATUS" == "ok" ]; then
  test_result "Liveness Check" "PASS" "Status: $LIVE_STATUS"
else
  test_result "Liveness Check" "FAIL" "Status: $LIVE_STATUS"
fi

READY_RESPONSE=$(curl -s "$BASE_URL/health/ready")
READY_STATUS=$(echo "$READY_RESPONSE" | jq -r '.status')
if [ "$READY_STATUS" == "ready" ]; then
  test_result "Readiness Check" "PASS" "Status: $READY_STATUS"
else
  test_result "Readiness Check" "FAIL" "Status: $READY_STATUS"
fi
echo

# === ЭТАП 3: Загрузка файла ===
echo -e "${YELLOW}[ЭТАП 3] Загрузка тестового файла...${NC}"
UPLOAD_RESPONSE=$(curl -s -X POST "$BASE_URL/api/v1/files/upload" \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@$TEST_FILE" \
  -F "description=Test file for LOCAL storage backend" \
  -F "version=1.0")

FILE_ID=$(echo "$UPLOAD_RESPONSE" | jq -r '.file_id')

if [ -z "$FILE_ID" ] || [ "$FILE_ID" == "null" ]; then
  test_result "Загрузка файла" "FAIL" "Не удалось получить file_id"
  echo -e "${RED}Response: $UPLOAD_RESPONSE${NC}"
else
  test_result "Загрузка файла" "PASS" "file_id: $FILE_ID"
fi
echo

# === ЭТАП 4: Получение метаданных ===
echo -e "${YELLOW}[ЭТАП 4] Получение метаданных файла...${NC}"
METADATA_RESPONSE=$(curl -s -X GET "$BASE_URL/api/v1/files/$FILE_ID" \
  -H "Authorization: Bearer $TOKEN")

ORIGINAL_FILENAME=$(echo "$METADATA_RESPONSE" | jq -r '.original_filename')
FILE_SIZE=$(echo "$METADATA_RESPONSE" | jq -r '.file_size')

if [ -n "$ORIGINAL_FILENAME" ] && [ "$ORIGINAL_FILENAME" != "null" ]; then
  test_result "Получение метаданных" "PASS" "Filename: $ORIGINAL_FILENAME, Size: $FILE_SIZE bytes"
else
  test_result "Получение метаданных" "FAIL" "Метаданные не получены"
fi
echo

# === ЭТАП 5: Скачивание файла ===
echo -e "${YELLOW}[ЭТАП 5] Скачивание файла...${NC}"
HTTP_CODE=$(curl -s -o "$DOWNLOADED_FILE" -w "%{http_code}" \
  -X GET "$BASE_URL/api/v1/files/$FILE_ID/download" \
  -H "Authorization: Bearer $TOKEN")

if [ "$HTTP_CODE" == "200" ]; then
  if diff "$TEST_FILE" "$DOWNLOADED_FILE" > /dev/null; then
    test_result "Скачивание файла" "PASS" "Содержимое совпадает"
  else
    test_result "Скачивание файла" "FAIL" "Содержимое НЕ совпадает"
  fi
else
  test_result "Скачивание файла" "FAIL" "HTTP $HTTP_CODE"
fi
echo

# === ЭТАП 6: Проверка checksum ===
echo -e "${YELLOW}[ЭТАП 6] Проверка контрольной суммы...${NC}"
if [ -f "$DOWNLOADED_FILE" ]; then
  ORIGINAL_SHA256=$(sha256sum "$TEST_FILE" | awk '{print $1}')
  DOWNLOADED_SHA256=$(sha256sum "$DOWNLOADED_FILE" | awk '{print $1}')

  if [ "$ORIGINAL_SHA256" == "$DOWNLOADED_SHA256" ]; then
    test_result "Проверка checksum" "PASS" "SHA256 совпадает"
  else
    test_result "Проверка checksum" "FAIL" "SHA256 не совпадает"
  fi
else
  test_result "Проверка checksum" "FAIL" "Скачанный файл не найден"
fi
echo

# === ЭТАП 7: Обновление метаданных ===
echo -e "${YELLOW}[ЭТАП 7] Обновление метаданных...${NC}"
UPDATE_RESPONSE=$(curl -s -X PATCH "$BASE_URL/api/v1/files/$FILE_ID" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "description": "Updated description for LOCAL test",
    "version": "1.1"
  }')

UPDATED_DESC=$(echo "$UPDATE_RESPONSE" | jq -r '.description')
UPDATED_VERSION=$(echo "$UPDATE_RESPONSE" | jq -r '.version')

if [ "$UPDATED_DESC" == "Updated description for LOCAL test" ] && [ "$UPDATED_VERSION" == "1.1" ]; then
  test_result "Обновление метаданных" "PASS" "Description и version обновлены"
else
  test_result "Обновление метаданных" "FAIL" "Метаданные не обновлены"
fi
echo

# === ЭТАП 8: Список файлов ===
echo -e "${YELLOW}[ЭТАП 8] Получение списка файлов...${NC}"
LIST_RESPONSE=$(curl -s -X GET "$BASE_URL/api/v1/files/?skip=0&limit=10" \
  -H "Authorization: Bearer $TOKEN")

TOTAL_FILES=$(echo "$LIST_RESPONSE" | jq -r '.total')

if [ "$TOTAL_FILES" -gt 0 ]; then
  test_result "Список файлов" "PASS" "Total: $TOTAL_FILES"
else
  test_result "Список файлов" "FAIL" "Список пуст"
fi
echo

# === ЭТАП 9: Удаление файла ===
echo -e "${YELLOW}[ЭТАП 9] Удаление файла...${NC}"
DELETE_HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" \
  -X DELETE "$BASE_URL/api/v1/files/$FILE_ID" \
  -H "Authorization: Bearer $TOKEN")

if [ "$DELETE_HTTP_CODE" == "204" ]; then
  test_result "Удаление файла" "PASS" "HTTP 204"
else
  test_result "Удаление файла" "FAIL" "HTTP $DELETE_HTTP_CODE"
fi

GET_DELETED_HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" \
  -X GET "$BASE_URL/api/v1/files/$FILE_ID" \
  -H "Authorization: Bearer $TOKEN")

if [ "$GET_DELETED_HTTP_CODE" == "404" ]; then
  test_result "Проверка удаления" "PASS" "HTTP 404"
else
  test_result "Проверка удаления" "FAIL" "HTTP $GET_DELETED_HTTP_CODE"
fi
echo

# === ЭТАП 10: Большой файл ===
echo -e "${YELLOW}[ЭТАП 10] Тест с большим файлом (10MB)...${NC}"
dd if=/dev/urandom of="$LARGE_FILE" bs=1M count=10 2>/dev/null

LARGE_UPLOAD_RESPONSE=$(curl -s -X POST "$BASE_URL/api/v1/files/upload" \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@$LARGE_FILE" \
  -F "description=Large test file 10MB")

LARGE_FILE_ID=$(echo "$LARGE_UPLOAD_RESPONSE" | jq -r '.file_id')

if [ -n "$LARGE_FILE_ID" ] && [ "$LARGE_FILE_ID" != "null" ]; then
  test_result "Загрузка большого файла" "PASS" "file_id: $LARGE_FILE_ID"

  curl -s -o /dev/null -X DELETE "$BASE_URL/api/v1/files/$LARGE_FILE_ID" \
    -H "Authorization: Bearer $TOKEN"
else
  test_result "Загрузка большого файла" "FAIL" "Не удалось загрузить"
fi
echo

# === ЭТАП 11: Негативные тесты ===
echo -e "${YELLOW}[ЭТАП 11] Негативные сценарии...${NC}"

NO_AUTH_CODE=$(curl -s -o /dev/null -w "%{http_code}" \
  -X GET "$BASE_URL/api/v1/files/")
if [ "$NO_AUTH_CODE" == "401" ]; then
  test_result "Запрос без токена" "PASS" "HTTP 401"
else
  test_result "Запрос без токена" "FAIL" "HTTP $NO_AUTH_CODE"
fi

FAKE_UUID="00000000-0000-0000-0000-000000000000"
FAKE_FILE_CODE=$(curl -s -o /dev/null -w "%{http_code}" \
  -X GET "$BASE_URL/api/v1/files/$FAKE_UUID" \
  -H "Authorization: Bearer $TOKEN")
if [ "$FAKE_FILE_CODE" == "404" ]; then
  test_result "Несуществующий файл" "PASS" "HTTP 404"
else
  test_result "Несуществующий файл" "FAIL" "HTTP $FAKE_FILE_CODE"
fi
echo

# === ОЧИСТКА ===
echo -e "${YELLOW}[ОЧИСТКА] Удаление временных файлов...${NC}"
rm -f "$TEST_FILE" "$DOWNLOADED_FILE" "$LARGE_FILE"
echo -e "${GREEN}Временные файлы удалены${NC}"
echo

# === ИТОГИ ===
echo -e "${YELLOW}========================================${NC}"
echo -e "${YELLOW}        ИТОГИ ТЕСТИРОВАНИЯ${NC}"
echo -e "${YELLOW}========================================${NC}"
echo -e "Всего тестов:    ${BLUE}$TOTAL_TESTS${NC}"
echo -e "Успешных:        ${GREEN}$PASSED_TESTS${NC}"
echo -e "Неудачных:       ${RED}$FAILED_TESTS${NC}"
echo

if [ "$FAILED_TESTS" -eq 0 ]; then
  echo -e "${GREEN}✓ Все тесты пройдены успешно! (100%)${NC}"
  exit 0
else
  PERCENTAGE=$((PASSED_TESTS * 100 / TOTAL_TESTS))
  echo -e "${YELLOW}⚠ Некоторые тесты не прошли. Успешность: $PERCENTAGE%${NC}"
  exit 1
fi
