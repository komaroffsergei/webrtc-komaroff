"""Configuration helpers for src_core service."""

from __future__ import annotations

import os
from pathlib import Path

STACK_SERVICE_NAME = os.getenv("STACK_SERVICE_NAME", "src_core")
CORE_PORT = int(os.getenv("CORE_PORT", "8000"))
CORE_HOST = os.getenv("CORE_HOST", "0.0.0.0")
NATS_URL = os.getenv("NATS_URL", "nats://localhost:4222")
ASR_MODELS_DIR = os.getenv("ASR_MODELS_DIR", "/app/models/asr")
ASR_MODEL_ID = os.getenv("ASR_MODEL_ID", "Systran/faster-whisper-small")
NATS_FRAMES_SUBJECT = os.getenv("NATS_FRAMES_SUBJECT", "nats.frames")
NATS_LOGS_SUBJECT = os.getenv("NATS_LOGS_SUBJECT", "nats.logs")
DEFAULT_VAD_DIR = Path(__file__).resolve().parents[1] / "models" / "vad"
VAD_MODEL_PATH = os.getenv("VAD_MODEL_PATH", str(DEFAULT_VAD_DIR))
VAD_MODEL_URL = os.getenv(
    "VAD_MODEL_URL",
    "https://github.com/snakers4/silero-vad/raw/refs/heads/master/src/silero_vad/data/silero_vad.onnx",
)
