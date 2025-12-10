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
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://192.168.2.108:11435")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "osmosis-mcp-4bQ8_0")

# ---- SYSTEM PROMPT ----
SYSTEM_PROMPT_FILE = os.getenv("SYSTEM_PROMPT_FILE", "system_prompt.txt")

# ---- LIMITS ----
MAX_OUTPUT_TOKENS = os.getenv("MAX_OUTPUT_TOKENS", 8096)
DEFAULT_MAX_TOKENS = os.getenv("DEFAULT_MAX_TOKENS", 2048)