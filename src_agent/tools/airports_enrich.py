import requests

from src_agent.settings import RUNWAYS_API_URL, TIMEOUT_SECONDS


def run(params):
    res = []

    for a in params.get("airports", []):
        airport_id = a["id"]

        # statuses
        s = requests.get(f"{RUNWAYS_API_URL}/{airport_id}/runways", timeout=TIMEOUT_SECONDS)
        s.raise_for_status()
        statuses = s.json()["runways"]
        has_free = any(r["status"] == "free" for r in statuses)

        # lengths
        l = requests.get(f"{RUNWAYS_API_URL}/{airport_id}/runway_lengths", timeout=TIMEOUT_SECONDS)
        l.raise_for_status()
        lengths = l.json()["runways"]
        max_len = max([x["length_m"] for x in lengths], default=0)

        a2 = dict(a)
        a2["has_free_runway"] = has_free
        a2["max_runway_length_m"] = max_len
        res.append(a2)

    return {"airports": res}
