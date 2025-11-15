"""
Performance testing fixtures and configuration.

Provides utilities for:
- Performance metrics collection
- Load testing scenarios
- Benchmark data generation
- Results reporting
"""

import pytest
import time
import asyncio
from typing import List, Dict, Any
from datetime import datetime, timezone
from dataclasses import dataclass, field
from statistics import mean, median, stdev
from pathlib import Path


@dataclass
class PerformanceMetric:
    """Single performance measurement."""
    operation: str
    duration_ms: float
    timestamp: datetime
    success: bool
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PerformanceReport:
    """Aggregated performance metrics report."""
    operation: str
    total_requests: int
    successful_requests: int
    failed_requests: int
    avg_latency_ms: float
    median_latency_ms: float
    p95_latency_ms: float
    p99_latency_ms: float
    min_latency_ms: float
    max_latency_ms: float
    std_dev_ms: float
    throughput_rps: float

    @property
    def success_rate_pct(self) -> float:
        """Calculate success rate percentage."""
        return (self.successful_requests / self.total_requests * 100) if self.total_requests > 0 else 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert report to dictionary."""
        return {
            "operation": self.operation,
            "total_requests": self.total_requests,
            "successful_requests": self.successful_requests,
            "failed_requests": self.failed_requests,
            "success_rate_pct": round(self.success_rate_pct, 2),
            "avg_latency_ms": round(self.avg_latency_ms, 2),
            "median_latency_ms": round(self.median_latency_ms, 2),
            "p95_latency_ms": round(self.p95_latency_ms, 2),
            "p99_latency_ms": round(self.p99_latency_ms, 2),
            "min_latency_ms": round(self.min_latency_ms, 2),
            "max_latency_ms": round(self.max_latency_ms, 2),
            "std_dev_ms": round(self.std_dev_ms, 2),
            "throughput_rps": round(self.throughput_rps, 2)
        }


class PerformanceCollector:
    """Collects and aggregates performance metrics."""

    def __init__(self):
        self.metrics: List[PerformanceMetric] = []

    def record(
        self,
        operation: str,
        duration_ms: float,
        success: bool = True,
        **metadata
    ):
        """Record a single performance metric."""
        metric = PerformanceMetric(
            operation=operation,
            duration_ms=duration_ms,
            timestamp=datetime.now(timezone.utc),
            success=success,
            metadata=metadata
        )
        self.metrics.append(metric)

    def get_report(self, operation: str = None) -> PerformanceReport:
        """Generate performance report for operation."""
        # Filter metrics
        filtered = self.metrics
        if operation:
            filtered = [m for m in self.metrics if m.operation == operation]

        if not filtered:
            raise ValueError(f"No metrics found for operation: {operation}")

        # Calculate statistics
        successful = [m for m in filtered if m.success]
        failed = [m for m in filtered if not m.success]
        durations = [m.duration_ms for m in filtered]

        # Sort for percentiles
        sorted_durations = sorted(durations)
        p95_idx = int(len(sorted_durations) * 0.95)
        p99_idx = int(len(sorted_durations) * 0.99)

        # Calculate throughput (requests per second)
        if len(filtered) > 1:
            time_span = (filtered[-1].timestamp - filtered[0].timestamp).total_seconds()
            throughput = len(filtered) / time_span if time_span > 0 else 0
        else:
            throughput = 0

        return PerformanceReport(
            operation=operation or "all",
            total_requests=len(filtered),
            successful_requests=len(successful),
            failed_requests=len(failed),
            avg_latency_ms=mean(durations),
            median_latency_ms=median(durations),
            p95_latency_ms=sorted_durations[p95_idx] if p95_idx < len(sorted_durations) else sorted_durations[-1],
            p99_latency_ms=sorted_durations[p99_idx] if p99_idx < len(sorted_durations) else sorted_durations[-1],
            min_latency_ms=min(durations),
            max_latency_ms=max(durations),
            std_dev_ms=stdev(durations) if len(durations) > 1 else 0,
            throughput_rps=throughput
        )

    def clear(self):
        """Clear all collected metrics."""
        self.metrics.clear()


@pytest.fixture
def performance_collector():
    """Performance metrics collector fixture."""
    collector = PerformanceCollector()
    yield collector
    collector.clear()


@pytest.fixture
def benchmark_timer():
    """Context manager for timing operations."""
    class Timer:
        def __init__(self):
            self.start_time = None
            self.end_time = None
            self.duration_ms = None

        def __enter__(self):
            self.start_time = time.perf_counter()
            return self

        def __exit__(self, *args):
            self.end_time = time.perf_counter()
            self.duration_ms = (self.end_time - self.start_time) * 1000

    return Timer


@pytest.fixture
def generate_test_file():
    """Generate test file with specified size."""
    def _generator(size_bytes: int, filename: str = "benchmark.bin") -> bytes:
        """
        Generate test file content.

        Args:
            size_bytes: File size in bytes
            filename: Filename for reference

        Returns:
            bytes: Generated file content
        """
        # Generate realistic data (not just zeros)
        import random
        import string

        # For small files, generate random text
        if size_bytes < 1024:
            return ''.join(random.choices(string.ascii_letters + string.digits, k=size_bytes)).encode()

        # For larger files, generate in chunks
        chunk_size = min(1024, size_bytes)
        chunks = []
        remaining = size_bytes

        while remaining > 0:
            current_chunk = min(chunk_size, remaining)
            chunk_data = ''.join(random.choices(string.ascii_letters + string.digits, k=current_chunk))
            chunks.append(chunk_data.encode())
            remaining -= current_chunk

        return b''.join(chunks)

    return _generator


@pytest.fixture
def load_test_scenario():
    """Execute load testing scenario."""
    async def _execute(
        operation: callable,
        concurrent_requests: int,
        total_requests: int,
        collector: PerformanceCollector,
        operation_name: str = "load_test"
    ):
        """
        Execute load testing scenario.

        Args:
            operation: Async callable to execute
            concurrent_requests: Number of concurrent requests
            total_requests: Total number of requests to execute
            collector: PerformanceCollector for metrics
            operation_name: Name for this operation
        """
        semaphore = asyncio.Semaphore(concurrent_requests)

        async def bounded_operation(request_id: int):
            async with semaphore:
                start = time.perf_counter()
                try:
                    await operation(request_id)
                    duration_ms = (time.perf_counter() - start) * 1000
                    collector.record(operation_name, duration_ms, success=True, request_id=request_id)
                except Exception as e:
                    duration_ms = (time.perf_counter() - start) * 1000
                    collector.record(operation_name, duration_ms, success=False, error=str(e), request_id=request_id)

        # Execute all requests
        tasks = [bounded_operation(i) for i in range(total_requests)]
        await asyncio.gather(*tasks)

    return _execute


@pytest.fixture
def performance_report_path(tmp_path):
    """Path for storing performance reports."""
    report_dir = tmp_path / "performance_reports"
    report_dir.mkdir(exist_ok=True)
    return report_dir


@pytest.fixture
def save_performance_report(performance_report_path):
    """Save performance report to file."""
    def _save(report: PerformanceReport, filename: str = None):
        """
        Save performance report.

        Args:
            report: PerformanceReport to save
            filename: Optional custom filename
        """
        import json

        if filename is None:
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            filename = f"perf_report_{report.operation}_{timestamp}.json"

        report_path = performance_report_path / filename

        with open(report_path, 'w') as f:
            json.dump(report.to_dict(), f, indent=2)

        return report_path

    return _save


# Performance test markers
def pytest_configure(config):
    """Register custom markers for performance tests."""
    config.addinivalue_line(
        "markers", "benchmark: mark test as a performance benchmark"
    )
    config.addinivalue_line(
        "markers", "load_test: mark test as a load testing scenario"
    )
    config.addinivalue_line(
        "markers", "slow: mark test as slow running (>1s)"
    )
