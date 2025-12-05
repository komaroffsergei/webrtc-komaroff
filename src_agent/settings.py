import os

STACK_SERVICE_NAME = os.getenv("STACK_SERVICE_NAME", "src_agent")

NATS_URL = os.getenv("NATS_URL", "nats://localhost:4222")

# Агент принимает запросы здесь
AGENT_FRAMES_SUBJECT = os.getenv("AGENT_FRAMES_SUBJECT", "agent.frames")

# Логи агента → сюда
AGENT_LOGS_SUBJECT = os.getenv("AGENT_LOGS_SUBJECT", "agent.logs")

# LLM сервис слушает здесь
LLM_FRAMES_SUBJECT = os.getenv("LLM_FRAMES_SUBJECT", "llm.frames")

# Лимит токенов на один шаг
AGENT_MAX_TOKENS = int(os.getenv("AGENT_MAX_TOKENS", "2048"))

MCP_HOST='localhost'
MCP_PORT=6006
MCP_URL='http://localhost:6006/mcp'