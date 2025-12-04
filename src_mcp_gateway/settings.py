import os
from dotenv import load_dotenv

load_dotenv()

AIRPORTS_API_URL = os.getenv("AIRPORTS_API_URL", "http://127.0.0.1:8100/api/airports/search")
RUNWAYS_API_URL = os.getenv("RUNWAYS_API_URL", "http://127.0.0.1:8100/api/airports")
PILOT_API_URL = os.getenv("PILOT_API_URL", "http://127.0.0.1:8100/api/pilot/location")
ROUTES_API_URL = os.getenv("ROUTES_API_URL", "http://127.0.0.1:8100/api/routes/nearest")

os.environ.setdefault("AIRPORTS_API_URL", AIRPORTS_API_URL)
os.environ.setdefault("RUNWAYS_API_URL", RUNWAYS_API_URL)
os.environ.setdefault("PILOT_API_URL", PILOT_API_URL)
os.environ.setdefault("ROUTES_API_URL", ROUTES_API_URL)

MCP_HOST = os.getenv("MCP_HOST", "127.0.0.1")
MCP_PORT = int(os.getenv("MCP_PORT", "6006"))

BACKEND_SSE_URL = os.getenv("BACKEND_SSE_URL", "http://127.0.0.1:8000/events")
SSE_RECONNECT_DELAY = float(os.getenv("BACKEND_SSE_RECONNECT", "1.0"))

NATS_URL = os.getenv("NATS_URL", "nats://localhost:4222")
NATS_LOGS_SUBJECT = os.getenv("NATS_LOGS_SUBJECT", "nats.logs")
