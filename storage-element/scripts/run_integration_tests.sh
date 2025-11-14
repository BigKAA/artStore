#!/bin/bash

# ==========================================
# Integration Tests Runner
# ==========================================
# Скрипт для запуска integration tests в Docker окружении
# с автоматической инициализацией БД через Alembic migrations
# ==========================================

set -e  # Exit on error

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "=================================================="
echo "Storage Element - Integration Tests Runner"
echo "=================================================="
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# ==========================================
# Step 1: Clean up previous test environment
# ==========================================
echo -e "${YELLOW}[1/6] Cleaning up previous test environment...${NC}"
cd "$PROJECT_ROOT"

docker-compose -f docker-compose.test.yml down -v 2>/dev/null || true
docker volume rm artstore_storage_postgres_test_data 2>/dev/null || true
docker volume rm artstore_storage_redis_test_data 2>/dev/null || true
docker volume rm artstore_storage_test_storage_data 2>/dev/null || true
docker volume rm artstore_storage_test_wal_data 2>/dev/null || true

echo -e "${GREEN}✓ Cleanup complete${NC}"
echo ""

# ==========================================
# Step 2: Start test infrastructure
# ==========================================
echo -e "${YELLOW}[2/6] Starting test infrastructure (PostgreSQL, Redis)...${NC}"

docker-compose -f docker-compose.test.yml up -d postgres-test redis-test

echo "Waiting for services to be healthy..."
sleep 5

# Wait for PostgreSQL to be ready
echo "Checking PostgreSQL health..."
for i in {1..30}; do
    if docker exec artstore_storage_postgres_test pg_isready -U artstore_test -d artstore_test &>/dev/null; then
        echo -e "${GREEN}✓ PostgreSQL is ready${NC}"
        break
    fi
    if [ $i -eq 30 ]; then
        echo -e "${RED}✗ PostgreSQL failed to start${NC}"
        exit 1
    fi
    sleep 1
done

# Wait for Redis to be ready
echo "Checking Redis health..."
for i in {1..30}; do
    if docker exec artstore_storage_redis_test redis-cli ping &>/dev/null; then
        echo -e "${GREEN}✓ Redis is ready${NC}"
        break
    fi
    if [ $i -eq 30 ]; then
        echo -e "${RED}✗ Redis failed to start${NC}"
        exit 1
    fi
    sleep 1
done

echo ""

# ==========================================
# Step 3: Run Alembic migrations
# ==========================================
echo -e "${YELLOW}[3/6] Running Alembic migrations...${NC}"

# Set environment variables for Alembic
export DB_HOST=localhost
export DB_PORT=5433
export DB_USERNAME=artstore_test
export DB_PASSWORD=test_password
export DB_DATABASE=artstore_test
export DB_TABLE_PREFIX=test_storage

# Activate virtual environment
if [ ! -d "$PROJECT_ROOT/../.venv" ]; then
    echo -e "${RED}✗ Virtual environment not found at $PROJECT_ROOT/../.venv${NC}"
    echo "Please create it first: python3 -m venv $PROJECT_ROOT/../.venv"
    exit 1
fi

source "$PROJECT_ROOT/../.venv/bin/activate"

# Run migrations
cd "$PROJECT_ROOT"
alembic upgrade head

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ Migrations applied successfully${NC}"
else
    echo -e "${RED}✗ Migrations failed${NC}"
    exit 1
fi

echo ""

# ==========================================
# Step 4: Start storage-element test service
# ==========================================
echo -e "${YELLOW}[4/6] Starting storage-element test service...${NC}"

docker-compose -f docker-compose.test.yml up -d storage-element-test

echo "Waiting for storage-element to be ready..."
for i in {1..60}; do
    if curl -f http://localhost:8011/health/live &>/dev/null; then
        echo -e "${GREEN}✓ Storage Element is ready${NC}"
        break
    fi
    if [ $i -eq 60 ]; then
        echo -e "${RED}✗ Storage Element failed to start${NC}"
        echo "Container logs:"
        docker logs artstore_storage_element_test --tail 50
        exit 1
    fi
    sleep 1
done

echo ""

# ==========================================
# Step 5: Run integration tests
# ==========================================
echo -e "${YELLOW}[5/6] Running integration tests...${NC}"

# Set environment variables for pytest
export JWT_PUBLIC_KEY_PATH="$PROJECT_ROOT/../admin-module/.keys/public_key.pem"
export DB_HOST=localhost
export DB_PORT=5433
export DB_USERNAME=artstore_test
export DB_PASSWORD=test_password
export DB_DATABASE=artstore_test
export REDIS_HOST=localhost
export REDIS_PORT=6380
export STORAGE_API_URL=http://localhost:8011

cd "$PROJECT_ROOT"
pytest tests/integration/ -v --tb=short --color=yes

TEST_EXIT_CODE=$?

echo ""

# ==========================================
# Step 6: Cleanup and results
# ==========================================
echo -e "${YELLOW}[6/6] Cleanup and results...${NC}"

if [ $TEST_EXIT_CODE -eq 0 ]; then
    echo -e "${GREEN}========================================${NC}"
    echo -e "${GREEN}✓ All integration tests passed!${NC}"
    echo -e "${GREEN}========================================${NC}"
else
    echo -e "${RED}========================================${NC}"
    echo -e "${RED}✗ Integration tests failed${NC}"
    echo -e "${RED}========================================${NC}"
    echo ""
    echo "Container logs:"
    docker logs artstore_storage_element_test --tail 100
fi

echo ""
echo "To cleanup test environment:"
echo "  docker-compose -f docker-compose.test.yml down -v"
echo ""
echo "To keep environment running for debugging:"
echo "  docker-compose -f docker-compose.test.yml ps"
echo "  docker logs artstore_storage_element_test -f"
echo ""

# Ask user if they want to keep the environment running
read -p "Keep test environment running? (y/N): " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Stopping test environment..."
    docker-compose -f docker-compose.test.yml down -v
    echo -e "${GREEN}✓ Test environment stopped${NC}"
fi

exit $TEST_EXIT_CODE
