FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip setuptools wheel \
    && pip install --no-cache-dir -r requirements.txt

COPY . /app/src_agent

ENV STACK_SERVICE_NAME=src_agent \
    USER_ID=user123 \
    NATS_URL=nats://localhost:4222 \
    NATS_EVENTS_SUBJECT=nats.events. \
    NATS_AGENT_SUBJECT=nats.agent. \
    NATS_LLM_SUBJECT=nats.llm. \
    AGENT_MAX_STEPS=10 \
    MAX_STEPS=10 \
    TIMEOUT_SECONDS=60 \
    OLLAMA_URL=http://localhost:11435 \
    OLLAMA_MODEL=qwen3:1.7b \
    DATABASE_URL=postgresql://mcp:mcp_pass@localhost:5432/mcp \
    AIRPORTS_API_URL=http://localhost:8100/api/airports/search \
    RUNWAYS_API_URL=http://localhost:8100/api/airports \
    PILOT_API_URL=http://localhost:8100/api/pilot/location \
    ROUTES_API_URL=http://localhost:8100/api/routes/nearest \
    WEATHER_API_URL=http://localhost:8100/api/weather

WORKDIR /app/src_agent

CMD ["python", "-m", "src_agent.main"]
