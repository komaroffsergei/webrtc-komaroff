import os
from dotenv import load_dotenv

from src_shared.contracts.subjects import Subjects

# Load environment variables from local .env (dev convenience).
current_dir = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(current_dir, ".env"))

USER_ID = os.getenv("USER_ID", "user123")

# NATS
NATS_URL = os.getenv("NATS_URL", "nats://localhost:4222")
NATS_AGENT_SUBJECT = os.getenv("NATS_AGENT_SUBJECT", Subjects.AGENT_PREFIX)
NATS_EVENTS_SUBJECT = os.getenv("NATS_EVENTS_SUBJECT", Subjects.EVENTS_PREFIX)
NATS_N8N_RUN_SUBJECT = os.getenv("NATS_N8N_RUN_SUBJECT", Subjects.N8N_RUN)

# Service
STACK_SERVICE_NAME = os.getenv("STACK_SERVICE_NAME", "src_agent")
N8N_TIMEOUT_SECONDS = int(os.getenv("N8N_TIMEOUT_SECONDS", "120"))
RUNTIME_CONFLICT_RETRIES = int(os.getenv("RUNTIME_CONFLICT_RETRIES", "3"))

# Database
POSTGRES_HOST = os.getenv("POSTGRES_HOST", "localhost")
POSTGRES_PORT = os.getenv("POSTGRES_PORT", "5432")
POSTGRES_DB = os.getenv("POSTGRES_DB", "mcp")
POSTGRES_USER = os.getenv("POSTGRES_USER", "mcp")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "mcp_pass")
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    f"postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}",
)
