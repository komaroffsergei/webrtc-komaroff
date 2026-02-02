"""Configuration helpers for src_whisper service."""

from __future__ import annotations

import os

STACK_SERVICE_NAME = os.getenv("STACK_SERVICE_NAME", "src_whisper_python")

NATS_URL = os.getenv("NATS_URL", "nats://localhost:4222")
NATS_EVENTS_SUBJECT = os.getenv("NATS_EVENTS_SUBJECT", "nats.events.")

ASR_IN_SUBSCRIBE = os.getenv("ASR_IN_SUBSCRIBE", "nats.asr.input.>")
ASR_IN_PREFIX = os.getenv("ASR_IN_PREFIX", "nats.asr.input.")
ASR_OUT_PREFIX = os.getenv("ASR_OUT_PREFIX", "nats.asr.output.")

WEBUI_ENABLED = os.getenv("WEBUI_ENABLED", "1").strip().lower() in {"1", "true", "yes", "on"}
WEBUI_HOST = os.getenv("WEBUI_HOST", "0.0.0.0")
WEBUI_PORT = int(os.getenv("WEBUI_PORT", "8090"))
WEBUI_BASE_PATH = os.getenv("WEBUI_BASE_PATH", "")

ASR_MODELS = os.getenv("ASR_MODELS", "models/asr")
ASR_MODEL_ID = os.getenv("ASR_MODEL_ID", "Systran/faster-whisper-small")

VAD_MODELS = os.getenv("VAD_MODELS", "models/vad")
VAD_MODEL_URL = os.getenv(
    "VAD_MODEL_URL",
    "https://github.com/snakers4/silero-vad/raw/refs/heads/master/src/silero_vad/data/silero_vad.onnx",
)

# Segmentation (Silero VAD) settings.
VAD_SAMPLE_RATE = int(os.getenv("VAD_SAMPLE_RATE", "16000"))
MIN_SPEECH_DURATION_MS = int(os.getenv("MIN_SPEECH_DURATION_MS", "250"))
MIN_SILENCE_DURATION_MS = int(os.getenv("MIN_SILENCE_DURATION_MS", "500"))
MAX_SPEECH_DURATION_S = float(os.getenv("MAX_SPEECH_DURATION_S", "30.0"))
SPEECH_PAD_MS = int(os.getenv("SPEECH_PAD_MS", "30"))
VAD_THRESHOLD = float(os.getenv("VAD_THRESHOLD", "0.8"))
BUFFER_CHECK_INTERVAL_S = float(os.getenv("BUFFER_CHECK_INTERVAL_S", "1.0"))

# Whisper settings.
WHISPER_LANGUAGE = os.getenv("WHISPER_LANGUAGE", "ru")
WHISPER_BEAM_SIZE = int(os.getenv("WHISPER_BEAM_SIZE", "1"))
WHISPER_MAX_CONCURRENCY = int(os.getenv("WHISPER_MAX_CONCURRENCY", "1"))
