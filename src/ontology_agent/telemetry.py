"""Tracing setup.

- ``APPLICATIONINSIGHTS_CONNECTION_STRING`` set  -> traces go to Azure Monitor (visible in Foundry tracing).
- ``OTEL_EXPORTER_OTLP_ENDPOINT`` set             -> traces go to any OTLP collector (e.g. Aspire dashboard).
- neither                                         -> tracing is a no-op.

Agent Framework emits spans for each agent run, model call and tool call. We add one
parent span per user request carrying route, prompt versions, tokens, cost and latency.
"""

from __future__ import annotations

import os

from opentelemetry import trace

_configured = False


def setup_telemetry(service_name: str = "foundry-ontology-agent") -> None:
    global _configured
    if _configured:
        return
    from agent_framework.observability import configure_otel_providers, enable_instrumentation

    if os.environ.get("APPLICATIONINSIGHTS_CONNECTION_STRING"):
        from azure.monitor.opentelemetry import configure_azure_monitor

        configure_azure_monitor()
        enable_instrumentation(enable_sensitive_data=False)
    elif os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT"):
        configure_otel_providers(service_name=service_name, enable_sensitive_data=False)
    _configured = True


tracer = trace.get_tracer("ontology_agent")
