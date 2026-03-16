from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

from src_shared.contracts.subjects import Subjects

current_dir = Path(__file__).parent.resolve()
env_file = current_dir / ".env"
env_local_file = current_dir / ".env.local"
load_dotenv(env_local_file if env_local_file.exists() else env_file)

USER_ID = os.getenv("USER_ID", "user123")
STACK_SERVICE_NAME = os.getenv("STACK_SERVICE_NAME", "src_langgraph")

NATS_URL = os.getenv("NATS_URL", "nats://localhost:4222")
NATS_LLM_SUBJECT_PREFIX = os.getenv("NATS_LLM_SUBJECT", Subjects.LLM_PREFIX)
NATS_TOOLS_PREFIX = os.getenv("NATS_TOOLS_PREFIX", Subjects.TOOLS_PREFIX)

NATS_WORKFLOW_RUN_SUBJECT = os.getenv("NATS_WORKFLOW_RUN_SUBJECT", Subjects.WORKFLOW_RUN)
NATS_WORKFLOW_HEALTH_SUBJECT = os.getenv("NATS_WORKFLOW_HEALTH_SUBJECT", Subjects.WORKFLOW_HEALTH)

NATS_REQUEST_TIMEOUT_SECONDS = float(os.getenv("NATS_REQUEST_TIMEOUT_SECONDS", "60"))
MAX_CONCURRENCY = int(os.getenv("MAX_CONCURRENCY", "8"))
MEMORY_RECENT_MESSAGES = int(os.getenv("MEMORY_RECENT_MESSAGES", "32"))
MEMORY_SUMMARY_MAX_CHARS = int(os.getenv("MEMORY_SUMMARY_MAX_CHARS", "12000"))
MEMORY_CONTEXT_MAX_CHARS = int(os.getenv("MEMORY_CONTEXT_MAX_CHARS", "18000"))
