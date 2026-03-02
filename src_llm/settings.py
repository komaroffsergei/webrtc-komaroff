"""Configuration helpers for src_core service."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

current_dir = Path(__file__).parent.resolve()
env_file = current_dir / '.env'
env_local_file = current_dir / '.env.local'
load_dotenv(env_local_file if os.path.exists(env_local_file) else env_file)

USER_ID = os.getenv("USER_ID", "user123")
STACK_SERVICE_NAME = os.getenv("STACK_SERVICE_NAME", "src_llm")

NATS_URL = os.getenv("NATS_URL", "nats://localhost:4222")
NATS_EVENTS_SUBJECT = os.getenv("NATS_EVENTS_SUBJECT", "nats.events.")
NATS_LLM_SUBJECT = os.getenv("NATS_LLM_SUBJECT", "nats.llm.")
NATS_AGENT_SUBJECT = os.getenv("NATS_AGENT_SUBJECT", "nats.agent.")

# ---- OLLAMA ----
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://ollama.h100.local")


LLM_MODE = os.getenv("LLM_MODE", "remote")
LLM_LOCAL_MODEL = os.getenv("LLM_LOCAL_MODEL", "Qwen/Qwen3-1.7B-GGUF")
LLM_REMOTE_MODEL = os.getenv("LLM_REMOTE_MODEL", "qwen3:30b")
LLM_MODELS = os.getenv("LLM_MODELS", "models/llm")
OLLAMA_MODEL_FILE = os.getenv("OLLAMA_MODEL_FILE", "")
LLM_CONTEXT_SIZE = int(os.getenv("LLM_CONTEXT_SIZE", "8192"))

# ---- LIMITS ----
MAX_OUTPUT_TOKENS = int(os.getenv("MAX_OUTPUT_TOKENS", "8096"))
DEFAULT_MAX_TOKENS = int(os.getenv("DEFAULT_MAX_TOKENS", "2048"))
