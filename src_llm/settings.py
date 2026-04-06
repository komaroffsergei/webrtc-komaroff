"""Configuration helpers for src_llm service."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

service_dir = Path(__file__).resolve().parent
load_dotenv(service_dir / ".env")
load_dotenv(service_dir / ".env.local", override=True)

USER_ID = os.getenv("USER_ID", "user123")
STACK_SERVICE_NAME = os.getenv("STACK_SERVICE_NAME", "src_llm")

NATS_URL = os.getenv("NATS_URL", "nats://localhost:4222")
NATS_EVENTS_SUBJECT = os.getenv("NATS_EVENTS_SUBJECT", "nats.events.")
NATS_LLM_SUBJECT = os.getenv("NATS_LLM_SUBJECT", "nats.llm.")

# ---- OLLAMA ----
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://ollama.h100.local")
OLLAMA_TIMEOUT_SECONDS = float(os.getenv("OLLAMA_TIMEOUT_SECONDS", "90"))


LLM_MODE = os.getenv("LLM_MODE", "remote")
LLM_LOCAL_MODEL = os.getenv("LLM_LOCAL_MODEL", "Qwen/Qwen3-1.7B-GGUF")
LLM_REMOTE_MODEL = os.getenv("LLM_REMOTE_MODEL", "qwen3:30b")
LLM_MODELS = os.getenv("LLM_MODELS", "models/llm")
OLLAMA_MODEL_FILE = os.getenv("OLLAMA_MODEL_FILE", "")
LLM_CONTEXT_SIZE = int(os.getenv("LLM_CONTEXT_SIZE", "16384"))

DEFAULT_MAX_TOKENS = int(os.getenv("DEFAULT_MAX_TOKENS", "2048"))
