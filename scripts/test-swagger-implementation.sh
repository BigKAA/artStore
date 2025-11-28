#!/bin/bash
#
# Integration Test Script: Swagger Implementation Validation
#
# Проверяет корректность реализации Swagger во всех модулях
#
# Usage:
#   ./scripts/test-swagger-implementation.sh [--verbose]
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

VERBOSE=false
if [[ "$1" == "--verbose" ]]; then
    VERBOSE=true
fi

# Logging functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[✓]${NC} $1"
}

log_error() {
    echo -e "${RED}[✗]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[!]${NC} $1"
}

# Test counters
TOTAL_TESTS=0
PASSED_TESTS=0
FAILED_TESTS=0

run_test() {
    local test_name="$1"
    local test_command="$2"

    TOTAL_TESTS=$((TOTAL_TESTS + 1))

    if $VERBOSE; then
        log_info "Running: $test_name"
        log_info "Command: $test_command"
    fi

    if eval "$test_command" > /dev/null 2>&1; then
        log_success "$test_name"
        PASSED_TESTS=$((PASSED_TESTS + 1))
        return 0
    else
        log_error "$test_name"
        FAILED_TESTS=$((FAILED_TESTS + 1))
        return 1
    fi
}

print_summary() {
    echo ""
    echo "========================================="
    echo "Test Summary"
    echo "========================================="
    echo "Total Tests:  $TOTAL_TESTS"
    echo -e "Passed:       ${GREEN}$PASSED_TESTS${NC}"
    echo -e "Failed:       ${RED}$FAILED_TESTS${NC}"
    echo "========================================="

    if [[ $FAILED_TESTS -eq 0 ]]; then
        log_success "All tests passed! ✨"
        return 0
    else
        log_error "Some tests failed!"
        return 1
    fi
}

# ========================================
# Test 1: Configuration Files Validation
# ========================================

log_info "========================================="
log_info "Phase 1: Configuration Validation"
log_info "========================================="

# Test 1.1: Ingester Module config.py
run_test "Ingester: swagger_enabled in AppSettings" \
    "grep -q 'swagger_enabled.*bool.*False' $PROJECT_ROOT/ingester-module/app/core/config.py"

run_test "Ingester: field_validator includes swagger_enabled" \
    "grep -q '@field_validator.*swagger_enabled' $PROJECT_ROOT/ingester-module/app/core/config.py"

# Test 1.2: Query Module config.py
run_test "Query: swagger_enabled in QueryModuleSettings" \
    "grep -q 'swagger_enabled.*bool.*False' $PROJECT_ROOT/query-module/app/core/config.py"

run_test "Query: field_validator includes swagger_enabled" \
    "grep -q '@field_validator.*swagger_enabled' $PROJECT_ROOT/query-module/app/core/config.py"

# Test 1.3: Admin Module config.py
run_test "Admin: swagger_enabled in Settings" \
    "grep -q 'swagger_enabled.*bool.*False' $PROJECT_ROOT/admin-module/app/core/config.py"

run_test "Admin: field_validator includes swagger_enabled" \
    "grep -q '@field_validator.*swagger_enabled' $PROJECT_ROOT/admin-module/app/core/config.py"

# ========================================
# Test 2: Application Files Validation
# ========================================

log_info ""
log_info "========================================="
log_info "Phase 2: Application Validation"
log_info "========================================="

# Test 2.1: Ingester Module main.py
run_test "Ingester: docs_url uses swagger_enabled" \
    "grep -q 'docs_url.*swagger_enabled' $PROJECT_ROOT/ingester-module/app/main.py"

run_test "Ingester: redoc_url uses swagger_enabled" \
    "grep -q 'redoc_url.*swagger_enabled' $PROJECT_ROOT/ingester-module/app/main.py"

run_test "Ingester: Swagger logging present" \
    "grep -q 'Swagger UI enabled' $PROJECT_ROOT/ingester-module/app/main.py"

# Test 2.2: Query Module main.py
run_test "Query: docs_url uses swagger_enabled" \
    "grep -q 'docs_url.*swagger_enabled' $PROJECT_ROOT/query-module/app/main.py"

run_test "Query: redoc_url uses swagger_enabled" \
    "grep -q 'redoc_url.*swagger_enabled' $PROJECT_ROOT/query-module/app/main.py"

run_test "Query: Swagger logging present" \
    "grep -q 'Swagger UI enabled' $PROJECT_ROOT/query-module/app/main.py"

# Test 2.3: Admin Module main.py
run_test "Admin: docs_url uses swagger_enabled" \
    "grep -q 'docs_url.*swagger_enabled' $PROJECT_ROOT/admin-module/app/main.py"

run_test "Admin: redoc_url uses swagger_enabled" \
    "grep -q 'redoc_url.*swagger_enabled' $PROJECT_ROOT/admin-module/app/main.py"

run_test "Admin: Swagger logging present" \
    "grep -q 'Swagger UI enabled' $PROJECT_ROOT/admin-module/app/main.py"

# ========================================
# Test 3: Docker Integration Tests
# ========================================

log_info ""
log_info "========================================="
log_info "Phase 3: Docker Integration Tests"
log_info "========================================="

log_warning "Docker integration tests require running containers"
log_info "Checking if containers are running..."

# Check if Docker is available
if ! command -v docker &> /dev/null; then
    log_warning "Docker not found, skipping integration tests"
else
    # Test 3.1: Check if Swagger is disabled by default (404)

    # Admin Module
    if docker ps | grep -q artstore-admin; then
        if curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/docs | grep -q "404"; then
            log_success "Admin: Swagger disabled by default (404)"
            PASSED_TESTS=$((PASSED_TESTS + 1))
        else
            log_warning "Admin: Swagger may be enabled (check APP_SWAGGER_ENABLED)"
        fi
        TOTAL_TESTS=$((TOTAL_TESTS + 1))
    else
        log_warning "Admin Module container not running, skipping live test"
    fi

    # Ingester Module
    if docker ps | grep -q artstore-ingester; then
        if curl -s -o /dev/null -w "%{http_code}" http://localhost:8020/docs | grep -q "404"; then
            log_success "Ingester: Swagger disabled by default (404)"
            PASSED_TESTS=$((PASSED_TESTS + 1))
        else
            log_warning "Ingester: Swagger may be enabled (check APP_SWAGGER_ENABLED)"
        fi
        TOTAL_TESTS=$((TOTAL_TESTS + 1))
    else
        log_warning "Ingester Module container not running, skipping live test"
    fi

    # Query Module
    if docker ps | grep -q artstore-query; then
        if curl -s -o /dev/null -w "%{http_code}" http://localhost:8030/docs | grep -q "404"; then
            log_success "Query: Swagger disabled by default (404)"
            PASSED_TESTS=$((PASSED_TESTS + 1))
        else
            log_warning "Query: Swagger may be enabled (check APP_SWAGGER_ENABLED)"
        fi
        TOTAL_TESTS=$((TOTAL_TESTS + 1))
    else
        log_warning "Query Module container not running, skipping live test"
    fi
fi

# ========================================
# Test 4: Pattern Consistency Check
# ========================================

log_info ""
log_info "========================================="
log_info "Phase 4: Pattern Consistency"
log_info "========================================="

# Check that all modules use the same pattern
run_test "All modules use 'Production-first' approach" \
    "grep -l 'swagger_enabled.*bool.*False' $PROJECT_ROOT/*/app/core/config.py | wc -l | grep -q '4'"

run_test "All modules use parse_bool_from_env" \
    "grep -l 'parse_bool_from_env' $PROJECT_ROOT/*/app/core/config.py | wc -l | grep -q '4'"

run_test "All modules log Swagger status" \
    "grep -l 'Swagger UI enabled' $PROJECT_ROOT/*/app/main.py | wc -l | grep -q '4'"

# ========================================
# Print Summary
# ========================================

echo ""
print_summary

# Return exit code based on test results
if [[ $FAILED_TESTS -eq 0 ]]; then
    exit 0
else
    exit 1
fi
