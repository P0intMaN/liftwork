"""OpenTelemetry + Prometheus wiring.

`configure_telemetry()` initialises the global OTel TracerProvider and
MeterProvider. Exporters are OTLP gRPC, addressable to any collector
(Datadog Agent, HyperDX, OTel Collector, Grafana Tempo) by setting
`LIFTWORK_TELEMETRY__OTEL_EXPORTER_OTLP_ENDPOINT`.

Prometheus metrics are exposed via a separate `prometheus_client`
registry that the API mounts at `/metrics`.
"""

from __future__ import annotations

from typing import Final

from opentelemetry import metrics, trace
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import (
    OTLPMetricExporter,
)
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
    OTLPSpanExporter,
)
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from prometheus_client import CONTENT_TYPE_LATEST, CollectorRegistry, generate_latest

from liftwork_core.config import TelemetrySettings

PROMETHEUS_REGISTRY: Final[CollectorRegistry] = CollectorRegistry(auto_describe=True)


def configure_telemetry(
    settings: TelemetrySettings,
    *,
    service_name: str | None = None,
    service_version: str | None = None,
) -> None:
    if not settings.otel_enabled:
        return

    attrs: dict[str, str] = {
        "service.name": service_name or settings.otel_service_name,
        "service.namespace": settings.otel_service_namespace,
    }
    if service_version:
        attrs["service.version"] = service_version
    resource = Resource.create(attrs)

    tracer_provider = TracerProvider(resource=resource)
    if settings.otel_exporter_otlp_endpoint:
        tracer_provider.add_span_processor(
            BatchSpanProcessor(
                OTLPSpanExporter(
                    endpoint=settings.otel_exporter_otlp_endpoint,
                    insecure=True,
                )
            )
        )
    trace.set_tracer_provider(tracer_provider)

    if settings.otel_exporter_otlp_endpoint:
        reader = PeriodicExportingMetricReader(
            OTLPMetricExporter(
                endpoint=settings.otel_exporter_otlp_endpoint,
                insecure=True,
            ),
            export_interval_millis=15_000,
        )
        meter_provider = MeterProvider(resource=resource, metric_readers=[reader])
        metrics.set_meter_provider(meter_provider)


def render_prometheus() -> tuple[bytes, str]:
    """Render the Prometheus exposition format for the shared registry."""
    return generate_latest(PROMETHEUS_REGISTRY), CONTENT_TYPE_LATEST
