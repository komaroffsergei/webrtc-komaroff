import os
from dotenv import load_dotenv

# Load environment variables
current_dir = os.path.dirname(os.path.abspath(__file__))
env_file = os.path.join(current_dir, '.env')
load_dotenv(env_file)

# NATS Configuration
NATS_URL = os.getenv("NATS_URL", "nats://localhost:4222")
NATS_AGENT_SUBJECT = os.getenv("NATS_AGENT_SUBJECT", "agent.requests")
NATS_LOGS_SUBJECT = os.getenv("NATS_LOGS_SUBJECT", "nats.logs")
NATS_LLM_SUBJECT = os.getenv("NATS_LLM_SUBJECT", "nats.frames")

# MCP Gateway Configuration
MCP_HOST = os.getenv("MCP_HOST", "127.0.0.1")
MCP_PORT = int(os.getenv("MCP_PORT", "6006"))
MCP_URL = os.getenv("MCP_URL", f"http://{MCP_HOST}:{MCP_PORT}/mcp")

# Agent settings
AGENT_MAX_STEPS = int(os.getenv("AGENT_MAX_STEPS", "10"))
STACK_SERVICE_NAME = os.getenv("STACK_SERVICE_NAME", "src_agent")