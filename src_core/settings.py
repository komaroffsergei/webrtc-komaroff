"""Configuration helpers for src_core service."""

from __future__ import annotations

import os

STACK_SERVICE_NAME = os.getenv("STACK_SERVICE_NAME", "src_core")

USER_ID = os.getenv("USER_ID", "user123")

NATS_URL = os.getenv("NATS_URL", "nats://localhost:4222")
NATS_EVENTS_SUBJECT = os.getenv("NATS_EVENTS_SUBJECT", "nats.events.")
NATS_AGENT_SUBJECT = os.getenv("NATS_AGENT_SUBJECT", "nats.agent.")
NATS_AGENT_HISTORY_SUBJECT = os.getenv("NATS_AGENT_HISTORY_SUBJECT", "nats.agent.history.")
NATS_REQUEST_TIMEOUT = float(os.getenv("NATS_REQUEST_TIMEOUT", "90"))
LIVE_ASR_COMMIT_IDLE_MS = int(os.getenv("LIVE_ASR_COMMIT_IDLE_MS", "1200"))

ASR_IN_PREFIX = "inference.whisper.stream."
ASR_OUT_PREFIX = "inference.whisper.text."

# When running src_core on the host while api-gateway is in Docker, use published port 8101.
API_URL = os.getenv("API_URL", "http://127.0.0.1:8101/api")

CORE_PORT = int(os.getenv("CORE_PORT", "8000"))
CORE_HOST = os.getenv("CORE_HOST", "0.0.0.0")

ASR_MODELS = os.getenv("ASR_MODELS", "/app/models/asr")
ASR_MODEL_ID = os.getenv("ASR_MODEL_ID", "Systran/faster-whisper-small")

# OpenTelemetry is opt-in for local development.
# Set OTEL_TRACES_EXPORTER=otlp and OTEL_EXPORTER_OTLP_ENDPOINT to enable exporting.
OTEL_EXPORTER_OTLP_ENDPOINT = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "")
OTEL_EXPORTER_OTLP_ENDPOINT_FRONT = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT_FRONT", "/v1/traces")
OTEL_LOG_LEVEL = os.getenv("OTEL_LOG_LEVEL", "debug")
OTEL_RESOURCE_ATTRIBUTES = os.getenv("OTEL_RESOURCE_ATTRIBUTES")
OTEL_TRACES_EXPORTER = os.getenv("OTEL_TRACES_EXPORTER", "none")
OTEL_METRICS_EXPORTER = os.getenv("OTEL_METRICS_EXPORTER")
