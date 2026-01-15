"""Configuration helpers for src_core service."""

from __future__ import annotations

import os
from pathlib import Path

STACK_SERVICE_NAME = os.getenv("STACK_SERVICE_NAME", "src_core")

USER_ID = os.getenv("USER_ID", "user123")

NATS_URL = os.getenv("NATS_URL", "nats://localhost:4222")
NATS_EVENTS_SUBJECT = os.getenv("NATS_EVENTS_SUBJECT", "nats.events.")
NATS_AGENT_SUBJECT = os.getenv("NATS_AGENT_SUBJECT", "nats.agent.")
NATS_ASR_SUBJECT = os.getenv("NATS_ASR_SUBJECT", "nats.asr.")
NATS_REQUEST_TIMEOUT = float(os.getenv("NATS_REQUEST_TIMEOUT", "600"))


CORE_PORT = int(os.getenv("CORE_PORT", "8000"))
CORE_HOST = os.getenv("CORE_HOST", "0.0.0.0")

ASR_MODELS_DIR = os.getenv("ASR_MODELS_DIR", "/app/models/asr")
ASR_MODEL_ID = os.getenv("ASR_MODEL_ID", "Systran/faster-whisper-small")

SERVICE_ROOT = Path(__file__).resolve().parent

# Keep VAD model under the src_core service root (works both locally and in Docker).
DEFAULT_VAD_DIR = SERVICE_ROOT / "models" / "vad"

_raw_vad_model_path = os.getenv("VAD_MODEL_PATH")
if _raw_vad_model_path:
    _candidate = Path(_raw_vad_model_path).expanduser()
    if not _candidate.is_absolute():
        _candidate = (SERVICE_ROOT / _candidate).resolve()
    elif _raw_vad_model_path.startswith("/app/") and not Path("/app").exists():
        _candidate = DEFAULT_VAD_DIR
    VAD_MODEL_PATH = str(_candidate)
else:
    VAD_MODEL_PATH = str(DEFAULT_VAD_DIR)
VAD_MODEL_URL = os.getenv(
    "VAD_MODEL_URL",
    "https://github.com/snakers4/silero-vad/raw/refs/heads/master/src/silero_vad/data/silero_vad.onnx",
)
