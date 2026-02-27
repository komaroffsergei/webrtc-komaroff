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
NATS_WORKFLOW_RUN_SUBJECT = os.getenv("NATS_WORKFLOW_RUN_SUBJECT", "nats.workflow.run")

# Service
STACK_SERVICE_NAME = os.getenv("STACK_SERVICE_NAME", "src_agent")
WORKFLOW_TIMEOUT_SECONDS = int(os.getenv("WORKFLOW_TIMEOUT_SECONDS", "120"))
RUNTIME_CONFLICT_RETRIES = int(os.getenv("RUNTIME_CONFLICT_RETRIES", "3"))

# Database
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://mcp:mcp_pass@localhost:5432/mcp")
