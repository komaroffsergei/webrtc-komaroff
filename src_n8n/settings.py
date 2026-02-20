import os
from dotenv import load_dotenv

from src_shared.contracts.subjects import Subjects

current_dir = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(current_dir, ".env"))

USER_ID = os.getenv("USER_ID", "user123")

STACK_SERVICE_NAME = os.getenv("STACK_SERVICE_NAME", "src_n8n")

NATS_URL = os.getenv("NATS_URL", "nats://localhost:4222")
NATS_N8N_RUN_SUBJECT = os.getenv("NATS_N8N_RUN_SUBJECT", Subjects.N8N_RUN)
NATS_N8N_HEALTH_SUBJECT = os.getenv("NATS_N8N_HEALTH_SUBJECT", Subjects.N8N_HEALTH)
NATS_LLM_SUBJECT_PREFIX = os.getenv("NATS_LLM_SUBJECT", Subjects.LLM_PREFIX)
NATS_TOOLS_PREFIX = os.getenv("NATS_TOOLS_PREFIX", Subjects.TOOLS_PREFIX)

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://mcp:mcp_pass@localhost:5432/mcp")
N8N_BASE_URL = os.getenv("N8N_BASE_URL", "http://n8n:5678")
N8N_WEBHOOK_BASE_URL = os.getenv("N8N_WEBHOOK_BASE_URL", "http://n8n_webhook:5678/webhook")
N8N_ENGINE_WORKFLOW_ID = os.getenv("N8N_ENGINE_WORKFLOW_ID", "Router1o0o0o0Abc")
N8N_ENGINE_WEBHOOK_PATH = os.getenv(
    "N8N_ENGINE_WEBHOOK_PATH",
    f"{N8N_ENGINE_WORKFLOW_ID}/webhook/router_1_0_0",
)

TOOL_PROXY_HOST = os.getenv("TOOL_PROXY_HOST", "0.0.0.0")
TOOL_PROXY_PORT = int(os.getenv("TOOL_PROXY_PORT", "9000"))

N8N_HTTP_TIMEOUT_SECONDS = float(os.getenv("N8N_HTTP_TIMEOUT_SECONDS", "120"))
