import requests

from src_agent.settings import RUNWAYS_API_URL, TIMEOUT_SECONDS


def run(params):
    airport_id = params["airport_id"]

    r1 = requests.get(f"{RUNWAYS_API_URL}/{airport_id}/runways", timeout=TIMEOUT_SECONDS)
    r1.raise_for_status()
    statuses = r1.json()["runways"]

    # Second service or same service endpoint
    r2 = requests.get(f"{RUNWAYS_API_URL}/{airport_id}/runway_lengths", timeout=TIMEOUT_SECONDS)
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
