"""
OpenTelemetry observability setup для Admin Module.

Provides distributed tracing и Prometheus metrics integration.
"""

import logging
from typing import Optional

from opentelemetry import trace, metrics
from opentelemetry.sdk.trace import TracerProvider
# BatchSpanProcessor будет использоваться при добавлении OTLP exporter
# from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.metrics import MeterProvider
# PeriodicExportingMetricReader будет использоваться при добавлении OTLP metrics exporter
# from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource, SERVICE_NAME, SERVICE_VERSION
from opentelemetry.exporter.prometheus import PrometheusMetricReader
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
# REGISTRY используется неявно через PrometheusMetricReader
# from prometheus_client import REGISTRY
from fastapi import FastAPI

logger = logging.getLogger(__name__)


def setup_observability(
    app: FastAPI,
    service_name: str,
    service_version: str,
    enable_tracing: bool = True,
    exporter_endpoint: Optional[str] = None  # TODO: будет использоваться для OTLP exporter
) -> None:
    """
    Настройка OpenTelemetry distributed tracing и Prometheus metrics.

    Args:
        app: FastAPI application instance
        service_name: Имя сервиса для идентификации в traces
        service_version: Версия сервиса
        enable_tracing: Включить distributed tracing
        exporter_endpoint: Endpoint для отправки traces (OTLP exporter) - TODO: не реализовано
    """
    # Resource для идентификации сервиса
    resource = Resource.create({
        SERVICE_NAME: service_name,
        SERVICE_VERSION: service_version,
    })

    # === Distributed Tracing Setup ===
    if enable_tracing:
        # Tracer Provider с resource
        tracer_provider = TracerProvider(resource=resource)

        # TODO: Добавить OTLP exporter если указан exporter_endpoint
        # from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
        # if exporter_endpoint:
        #     otlp_exporter = OTLPSpanExporter(endpoint=exporter_endpoint)
        #     tracer_provider.add_span_processor(BatchSpanProcessor(otlp_exporter))

        # Установка глобального tracer provider
        trace.set_tracer_provider(tracer_provider)

        logger.info(
            "OpenTelemetry tracing initialized",
            extra={"service_name": service_name, "version": service_version}
        )

    # === Prometheus Metrics Setup ===
    # Prometheus metric reader для экспорта метрик
    prometheus_reader = PrometheusMetricReader()

    # Meter Provider с Prometheus exporter
    meter_provider = MeterProvider(
        resource=resource,
        metric_readers=[prometheus_reader]
    )

    # Установка глобального meter provider
    metrics.set_meter_provider(meter_provider)

    logger.info(
        "Prometheus metrics initialized",
        extra={"service_name": service_name, "registry": "REGISTRY"}
    )

    # === FastAPI Instrumentation ===
    # Автоматическое инструментирование HTTP endpoints
    FastAPIInstrumentor.instrument_app(app)

    logger.info(
        "FastAPI instrumentation complete",
        extra={"service_name": service_name, "tracing_enabled": enable_tracing}
    )


def get_tracer(name: str) -> trace.Tracer:
    """
    Получить tracer для создания custom spans.

    Args:
        name: Имя tracer (обычно __name__ модуля)

    Returns:
        Tracer instance для создания spans

    Example:
        >>> tracer = get_tracer(__name__)
        >>> with tracer.start_as_current_span("operation_name"):
        ...     # Your code here
        ...     pass
    """
    return trace.get_tracer(name)


def get_meter(name: str) -> metrics.Meter:
    """
    Получить meter для создания custom metrics.

    Args:
        name: Имя meter (обычно __name__ модуля)

    Returns:
        Meter instance для создания метрик

    Example:
        >>> meter = get_meter(__name__)
        >>> counter = meter.create_counter("requests_total")
        >>> counter.add(1, {"endpoint": "/api/v1/users"})
    """
    return metrics.get_meter(name)
