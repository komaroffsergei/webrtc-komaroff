"""Configuration helpers for src_whisper service."""

from __future__ import annotations

import os

STACK_SERVICE_NAME = os.getenv("STACK_SERVICE_NAME", "src_whisper_python")

USER_ID = os.getenv("USER_ID", "user123")

NATS_URL = os.getenv("NATS_URL", "nats://localhost:4222")
NATS_EVENTS_SUBJECT = os.getenv("NATS_EVENTS_SUBJECT", "nats.events.")
NATS_ASR_SUBJECT = os.getenv("NATS_ASR_SUBJECT", "nats.asr.")

ASR_MODELS_DIR = os.getenv("ASR_MODELS_DIR", "/app/models/asr")
ASR_MODEL_ID = os.getenv("ASR_MODEL_ID", "Systran/faster-whisper-small")
