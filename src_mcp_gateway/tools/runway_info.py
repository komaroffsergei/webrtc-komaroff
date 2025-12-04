import requests

from src_mcp_gateway.config_loader import load_settings

SETTINGS = load_settings()
API = SETTINGS["services"]["runways_api"]
TIMEOUT = SETTINGS["network"]["timeout_seconds"]

def run(params):
    airport_id = params["airport_id"]

    r1 = requests.get(f"{API}/{airport_id}/runways", timeout=TIMEOUT)
    r1.raise_for_status()
    statuses = r1.json()["runways"]

    # Second service or same service endpoint
    r2 = requests.get(f"{API}/{airport_id}/runway_lengths", timeout=TIMEOUT)
    r2.raise_for_status()
    lengths = r2.json()["runways"]

    # merge
    length_map = {x["runway_id"]: x["length_m"] for x in lengths}

    final = []
    for s in statuses:
        rid = s["runway_id"]
        final.append({
            "runway_id": rid,
            "status": s["status"],
            "length_m": length_map.get(rid, 0)
        })

    return {"runways": final}
