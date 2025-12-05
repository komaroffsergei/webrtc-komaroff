import requests
from src_mcp_gateway.config_loader import load_settings

SETTINGS = load_settings()
API = SETTINGS["services"]["runways_api"]
TIMEOUT = SETTINGS["network"]["timeout_seconds"]


def run(params):
    """
    MCP-tool: получить длины ВПП аэропорта.
    params = { "airport_id": "UUWW" }
    """

    airport_id = params["airport_id"]

    url = f"{API}/{airport_id}/runway_lengths"

    r = requests.get(url, timeout=TIMEOUT)
    r.raise_for_status()

    data = r.json()
    runways = data.get("runways", [])

    # normalize
    out = []
    for rw in runways:
        out.append({
            "runway_id": rw["runway_id"],
            "length_m": rw["length_m"]
        })

    return {"runways": out}
