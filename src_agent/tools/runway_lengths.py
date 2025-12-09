import requests

from src_agent.settings import RUNWAYS_API_URL, TIMEOUT_SECONDS


def run(params):
    """
    MCP-tool: получить длины ВПП аэропорта.
    params = { "airport_id": "UUWW" }
    """

    airport_id = params["airport_id"]

    url = f"{RUNWAYS_API_URL}/{airport_id}/runway_lengths"

    r = requests.get(url, timeout=TIMEOUT_SECONDS)
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
