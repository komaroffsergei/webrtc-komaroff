import asyncio
import json
import os
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Any, Dict
from dotenv import load_dotenv
import uvicorn

from src_mcp_gateway.tools import get_airport_by_name, error_report, get_current_position

# Поднимаем переменные окружения
load_dotenv()

AIRPORTS_API_URL = os.getenv("AIRPORTS_API_URL", "http://127.0.0.1:8100/api/airports/search")
RUNWAYS_API_URL = os.getenv("RUNWAYS_API_URL", "http://127.0.0.1:8100/api/airports")
MCP_HOST = os.getenv("MCP_HOST", "127.0.0.1")
MCP_PORT = int(os.getenv("MCP_PORT", "6006"))

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MANIFEST_PATH = os.path.join(BASE_DIR, "manifest.json")
# Грузим манифест
with open(MANIFEST_PATH, "r") as f:
    MANIFEST = json.load(f)

# Инструменты
from tools.search_airports import run as search_airports_run
from tools.get_runway_status import run as get_runway_status_run
from tools.compute_distance import run as compute_distance_run

TOOLS = {
    "search_airports": search_airports_run,
    "get_runway_status": get_runway_status_run,
    "compute_distance": compute_distance_run,
    "get_airport_by_name": get_airport_by_name,
    "error_report": error_report,
    "get_current_position": get_current_position
}

# FastAPI
app = FastAPI()

class InvokeRequest(BaseModel):
    tool: str
    params: Dict[str, Any]


@app.get("/manifest")
def get_manifest():
    return MANIFEST


@app.post("/invoke")
def invoke_tool(request: InvokeRequest):
    tool_name = request.tool
    params = request.params

    if tool_name not in TOOLS:
        raise HTTPException(status_code=400, detail=f"Unknown tool: {tool_name}")

    try:
        result = TOOLS[tool_name](params)
        return {"result": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


config = uvicorn.Config(
    "main:app",
    host=MCP_HOST,
    port=MCP_PORT,
    reload=False,
)

server = uvicorn.Server(config)

if __name__ == "__main__":
    asyncio.run(server.serve())