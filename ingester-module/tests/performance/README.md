# Performance Testing - Ingester Module

## Overview

Comprehensive performance benchmarks and load testing suite for Ingester Module to establish performance baselines and identify bottlenecks.

## Test Categories

### Benchmark Tests (`@pytest.mark.benchmark`)

Single-operation latency measurements with strict performance targets.

#### Upload Latency Benchmarks

| Test | File Size | Target | Measures |
|------|-----------|--------|----------|
| `test_upload_latency_small_file` | 10 KB | <50ms | Small file processing speed |
| `test_upload_latency_medium_file` | 1 MB | <200ms | Medium file handling |
| `test_upload_latency_large_file` | 10 MB | <500ms | Large file throughput |

#### Authentication Overhead Benchmarks

| Test | Operation | Target | Measures |
|------|-----------|--------|----------|
| `test_jwt_validation_latency` | JWT RS256 validation | <10ms | Auth overhead per request |

### Load Tests (`@pytest.mark.load_test`)

Concurrent user scenarios measuring throughput and scalability under load.

| Test | Concurrent Users | Total Requests | Target Throughput | Target Latency |
|------|-----------------|----------------|-------------------|----------------|
| `test_concurrent_uploads_10_users` | 10 | 100 | >50 RPS | <200ms avg |
| `test_concurrent_uploads_50_users` | 50 | 500 | >100 RPS | <500ms avg |

## Running Tests

### Quick Benchmarks (Fast)

```bash
# Activate virtual environment
source /home/artur/Projects/artStore/.venv/bin/activate

# Run only benchmark tests (no load tests)
pytest tests/performance/ -m benchmark -v

# Run specific benchmark
pytest tests/performance/test_upload_performance.py::TestUploadPerformance::test_upload_latency_small_file -v
```

### Load Tests (Slow, >30s)

```bash
# Run load tests (marked as slow)
pytest tests/performance/ -m load_test -v

# Run specific load test
pytest tests/performance/test_upload_performance.py::TestUploadThroughput::test_concurrent_uploads_10_users -v
```

### All Performance Tests

```bash
# Run everything (benchmarks + load tests)
pytest tests/performance/ -v
```

## Performance Metrics Collected

### Latency Metrics

- **Average Latency**: Mean response time across all requests
- **Median Latency**: 50th percentile (half of requests faster/slower)
- **P95 Latency**: 95th percentile (95% of requests faster)
- **P99 Latency**: 99th percentile (99% of requests faster)
- **Min/Max Latency**: Best and worst case response times
- **Standard Deviation**: Response time consistency

### Throughput Metrics

- **Requests Per Second (RPS)**: Total throughput under load
- **Success Rate %**: Percentage of successful operations
- **Failed Requests**: Count of failed operations with error details

## Performance Reports

Tests automatically generate JSON performance reports in `tmp_path/performance_reports/`:

```json
{
  "operation": "concurrent_upload_10",
  "total_requests": 100,
  "successful_requests": 100,
  "failed_requests": 0,
  "success_rate_pct": 100.0,
  "avg_latency_ms": 45.32,
  "median_latency_ms": 42.15,
  "p95_latency_ms": 78.90,
  "p99_latency_ms": 95.44,
  "min_latency_ms": 15.20,
  "max_latency_ms": 120.55,
  "std_dev_ms": 18.75,
  "throughput_rps": 125.43
}
```

## Baseline Performance Targets

### Upload Operations

| File Size | Avg Latency | P95 Latency | Notes |
|-----------|-------------|-------------|-------|
| 10 KB | <50ms | <100ms | Typical document upload |
| 1 MB | <200ms | <400ms | Image/PDF upload |
| 10 MB | <500ms | <1000ms | Large file/video upload |

### Authentication

| Operation | Avg Latency | P95 Latency | Notes |
|-----------|-------------|-------------|-------|
| JWT Validation | <10ms | <20ms | Per-request auth overhead |

### Concurrent Load

| Scenario | Throughput | Success Rate | Notes |
|----------|------------|--------------|-------|
| 10 concurrent users | >50 RPS | >95% | Normal load |
| 50 concurrent users | >100 RPS | >90% | High load |

## Performance Testing Framework

### Custom Fixtures

#### `performance_collector`

Collects and aggregates performance metrics across test operations:

```python
@pytest.mark.asyncio
async def test_my_operation(performance_collector, benchmark_timer):
    with benchmark_timer() as timer:
        # Execute operation
        await my_operation()

    # Record metric
    performance_collector.record("my_operation", timer.duration_ms)

    # Generate report
    report = performance_collector.get_report("my_operation")
    assert report.avg_latency_ms < 100
```

#### `benchmark_timer`

Context manager for accurate operation timing:

```python
with benchmark_timer() as timer:
    await operation()
print(f"Duration: {timer.duration_ms}ms")
```

#### `generate_test_file`

Generate test files of specified size with realistic data:

```python
def test_upload(generate_test_file):
    file_content = generate_test_file(1024 * 1024)  # 1MB
    # Use file_content for upload testing
```

#### `load_test_scenario`

Execute concurrent load testing scenarios:

```python
async def test_load(load_test_scenario, performance_collector):
    async def operation(request_id):
        # Single operation logic
        await upload_file(f"file_{request_id}")

    await load_test_scenario(
        operation=operation,
        concurrent_requests=10,
        total_requests=100,
        collector=performance_collector,
        operation_name="my_load_test"
    )

    report = performance_collector.get_report("my_load_test")
```

#### `save_performance_report`

Save performance reports to JSON files:

```python
def test_benchmark(performance_collector, save_performance_report):
    # ... execute operations ...
    report = performance_collector.get_report("operation")
    save_performance_report(report, "my_benchmark.json")
```

## Interpreting Results

### Latency Analysis

- **P95 < Target**: 95% of requests meet performance target (good)
- **P99 >> P95**: Occasional outliers, investigate error handling
- **High Std Dev**: Inconsistent performance, check for bottlenecks

### Throughput Analysis

- **Success Rate < 95%**: System overloaded or errors present
- **RPS < Target**: Performance bottleneck identified
- **Increasing Latency with Load**: Scalability issue

### Common Performance Issues

| Symptom | Likely Cause | Investigation |
|---------|--------------|---------------|
| High avg latency | Slow external calls | Check HTTP client timeouts |
| High P99 latency | Occasional timeouts | Review error logs |
| Low throughput | Connection pooling | Verify HTTP/2 connections |
| Failed requests | Resource exhaustion | Check memory/CPU usage |

## Continuous Performance Monitoring

### CI/CD Integration

```yaml
# Example GitHub Actions workflow
- name: Run Performance Benchmarks
  run: |
    pytest tests/performance/ -m benchmark -v --json-report --json-report-file=perf_report.json

- name: Check Performance Regression
  run: |
    python scripts/check_performance_regression.py perf_report.json baseline_perf.json
```

### Performance Regression Detection

Compare current performance against baselines:

```bash
# Store baseline
pytest tests/performance/ -m benchmark --json-report --json-report-file=baseline.json

# Run current tests
pytest tests/performance/ -m benchmark --json-report --json-report-file=current.json

# Compare (manual for now, automated script TODO)
diff baseline.json current.json
```

## Best Practices

1. **Consistent Environment**: Run performance tests in isolated environment (Docker container)
2. **Multiple Runs**: Execute benchmarks 3-5 times, use median results
3. **Realistic Data**: Use representative file sizes and content types
4. **Monitor Resources**: Track CPU, memory, I/O during load tests
5. **Baseline Updates**: Update baselines when intentional performance improvements are made
6. **Failure Investigation**: Always investigate failed load tests - may indicate real issues

## Troubleshooting

### Tests Timeout

**Symptom**: Tests exceed 30s pytest timeout.

**Solution**: Mark slow tests with `@pytest.mark.slow` and increase timeout:
```python
@pytest.mark.slow
@pytest.mark.timeout(60)
async def test_very_slow_operation():
    ...
```

### Inconsistent Results

**Symptom**: Large variance in latency between runs.

**Solutions**:
- Run tests in Docker container (isolated environment)
- Disable system background processes
- Use dedicated testing machine
- Increase sample size (more total_requests)

### Out of Memory

**Symptom**: Load tests fail with memory errors.

**Solutions**:
- Reduce concurrent_requests
- Use smaller test file sizes
- Add explicit cleanup between operations
- Monitor memory usage with profiler

## Future Enhancements

- [ ] Automated performance regression detection in CI/CD
- [ ] Real Storage Element integration (vs mocks)
- [ ] Network latency simulation (slow 3G, 4G)
- [ ] Memory profiling and leak detection
- [ ] CPU profiling with flame graphs
- [ ] Comparison reports (baseline vs current)
- [ ] Performance dashboards (Grafana integration)
- [ ] Stress testing (>100 concurrent users)

## Contact

For questions about performance testing, check project documentation or contact the development team.
