# Sprint 10: Testing Infrastructure Enhancement Plan

**Дата начала**: 2025-11-14
**Цель**: Улучшить тестовую инфраструктуру Storage Element для достижения 70% coverage и автоматизации CI/CD
**Предыдущий Sprint**: Sprint 9 - 100% Integration Test Success (31/31 passing)

## Текущее состояние

### Coverage Metrics (Baseline)
- **Overall Coverage**: 47% (1435 statements, 701 missed)
- **Models**: 96-98% ✅ (отличное покрытие)
- **Utils**: 12-82% (mixed, требует внимания)
- **Services**: 11-39% ⚠️ (критическая зона)
- **API Endpoints**: 35% (требует больше integration tests)

### Критические низкопокрытые модули
1. **file_service.py**: 11% (182 statements, 158 missed)
2. **wal_service.py**: 15% (99 statements, 82 missed)
3. **file_naming.py**: 12% (66 statements, 56 missed)
4. **attr_utils.py**: 31% (112 statements, 71 missed)
5. **storage_service.py**: 39% (198 statements, 117 missed)

### Integration Tests Status
- **Total**: 31/31 passing (100% ✅)
- **Architecture**: Real HTTP requests через Docker test container
- **Environment**: Proper test/production isolation

## Sprint 10 Tasks (4 Phases)

### Phase 1: Service Layer Smoke Tests (Priority: P0)
**Goal**: 47% → 60% coverage через тестирование happy paths

**Tasks**:
1. **file_service.py smoke tests** (11% → 50%)
   - `test_upload_file_happy_path` - successful upload flow
   - `test_get_file_metadata_happy_path` - successful metadata retrieval
   - `test_delete_file_happy_path` - successful deletion
   - `test_list_files_pagination` - pagination logic

2. **wal_service.py smoke tests** (15% → 50%)
   - `test_create_wal_entry_happy_path` - WAL entry creation
   - `test_commit_wal_entry` - successful commit
   - `test_rollback_wal_entry` - successful rollback
   - `test_wal_state_machine` - state transitions

3. **storage_service.py smoke tests** (39% → 60%)
   - `test_write_file_happy_path` - file write to local storage
   - `test_read_file_happy_path` - file read from storage
   - `test_ensure_directory_structure` - directory creation logic

**Estimated Coverage Gain**: +13% (47% → 60%)

### Phase 2: Utils Full Coverage (Priority: P1)
**Goal**: 60% → 65% coverage через тестирование utility функций

**Tasks**:
1. **file_naming.py tests** (12% → 95%)
   - `test_generate_storage_filename` - all scenarios
   - `test_generate_storage_filename_long_names` - edge case
   - `test_generate_storage_filename_special_chars` - sanitization
   - `test_parse_storage_filename` - reverse operation
   - `test_generate_unique_filename_collision_prevention`

2. **attr_utils.py tests** (31% → 90%)
   - `test_write_attr_file_atomic` - atomic write verification
   - `test_read_attr_file` - successful read
   - `test_attr_file_validation` - schema validation
   - `test_attr_file_size_limit` - 4KB limit enforcement

**Estimated Coverage Gain**: +5% (60% → 65%)

### Phase 3: Automated CI/CD Pipeline (Priority: P1)
**Goal**: Автоматизация тестирования при каждом commit/PR

**Tasks**:
1. **GitHub Actions Workflow** (`.github/workflows/storage-element-tests.yml`)
   ```yaml
   name: Storage Element Tests
   on: [push, pull_request]
   jobs:
     test:
       runs-on: ubuntu-latest
       steps:
         - uses: actions/checkout@v3
         - name: Start test containers
           run: cd storage-element && docker-compose -f docker-compose.test.yml up -d
         - name: Wait for services
           run: sleep 30
         - name: Run integration tests
           run: |
             cd storage-element
             source ../.venv/bin/activate
             pytest tests/integration/ -v --cov=app --cov-report=xml
         - name: Upload coverage to Codecov
           uses: codecov/codecov-action@v3
   ```

2. **Pre-commit Hooks** (`.pre-commit-config.yaml`)
   - Automatic unit tests on commit
   - Coverage threshold check (minimum 60%)
   - Code formatting (black, isort)

3. **Quality Gates**
   - Minimum coverage: 60%
   - All integration tests must pass
   - No critical security vulnerabilities (bandit)

**Deliverable**: Automated testing pipeline

### Phase 4: Performance Testing Infrastructure (Priority: P2)
**Goal**: Baseline performance metrics для future optimization

**Tasks**:
1. **Locust Load Testing** (`tests/performance/locustfile.py`)
   ```python
   from locust import HttpUser, task, between

   class StorageElementUser(HttpUser):
       wait_time = between(1, 3)

       @task(3)
       def upload_file(self):
           """Test file upload performance"""
           with open("test_file.bin", "rb") as f:
               self.client.post("/api/v1/files/upload",
                   files={"file": f},
                   headers=self.auth_headers)

       @task(5)
       def search_files(self):
           """Test search performance"""
           self.client.get("/api/v1/files/search?query=test")
   ```

2. **Performance Benchmarks**
   - Upload throughput: Target 50 MB/s (single file)
   - Search latency: Target <100ms (p95)
   - Download throughput: Target 100 MB/s
   - Concurrent uploads: Target 50 simultaneous

3. **Monitoring Integration**
   - Prometheus metrics collection
   - Grafana dashboard для visualization
   - Alerting на performance degradation

**Deliverable**: Performance baseline для Sprint 11 optimization

## Expected Outcomes

### Coverage Targets
- **Phase 1 Complete**: 47% → 60% ✅
- **Phase 2 Complete**: 60% → 65% ✅
- **Overall Target**: 65%+ (18% improvement)

### Quality Metrics
- ✅ 100% Integration Tests Passing (maintained)
- ✅ Automated CI/CD Pipeline (GitHub Actions)
- ✅ Performance Baseline Established
- ✅ Pre-commit Quality Gates

### Testing Best Practices
```python
# ✅ Service Layer Smoke Test Pattern
async def test_service_happy_path():
    """Test successful operation flow"""
    result = await service.operation(valid_input)
    assert result.success is True
    assert result.data is not None

# ✅ Utils Test Pattern
def test_utility_function():
    """Test utility with edge cases"""
    # Happy path
    assert utility_fn(normal_input) == expected_output
    # Edge cases
    assert utility_fn(edge_case) == edge_output
    # Error handling
    with pytest.raises(ExpectedError):
        utility_fn(invalid_input)
```

## Success Criteria

1. ✅ **Coverage**: 47% → 65%+ (achieved through smoke tests)
2. ✅ **Automation**: GitHub Actions CI/CD pipeline running
3. ✅ **Performance**: Baseline metrics established for all critical operations
4. ✅ **Quality Gates**: Pre-commit hooks preventing regression
5. ✅ **Documentation**: Testing best practices documented

## Timeline

- **Week 1 (Days 1-2)**: Phase 1 - Service Layer Smoke Tests
- **Week 1 (Days 3-4)**: Phase 2 - Utils Full Coverage
- **Week 2 (Days 1-2)**: Phase 3 - CI/CD Pipeline
- **Week 2 (Day 3)**: Phase 4 - Performance Infrastructure
- **Total Estimated Time**: 7 days

## Dependencies

- ✅ Sprint 9 Complete (100% integration tests)
- ✅ Docker test environment functional
- ✅ Production container updated with latest code
- ⏳ GitHub repository (for Actions)
- ⏳ Codecov account (optional, for coverage tracking)

## Risks & Mitigation

**Risk 1**: Service layer tests may reveal bugs in production code
- **Mitigation**: Fix bugs as discovered, update production container

**Risk 2**: Performance tests may overwhelm test infrastructure
- **Mitigation**: Use dedicated performance test environment, limit concurrent users

**Risk 3**: CI/CD pipeline may slow down development
- **Mitigation**: Optimize test execution time, run heavy tests only on PR

## Next Steps After Sprint 10

**Sprint 11 Options**:
1. **Ingester Module Foundation** - начать разработку нового модуля
2. **Storage Element Optimization** - использовать performance baseline для улучшений
3. **Admin Module Enhancement** - добавить недостающие features

**Recommended**: Sprint 11 → Ingester Module Foundation (roadmap alignment)
