import requests

from src_mcp_gateway.config_loader import load_settings

SETTINGS = load_settings()
API_URL = SETTINGS["services"]["airports_api"]
TIMEOUT = SETTINGS["network"]["timeout_seconds"]


def run(params):
    """
    Поиск аэропорта по имени или его части.

    Вход:
      { "query": str }

    Выход:
      { "results": [ {id, name, lat, lon}, ... ] }
    """
    query = str(params["query"]).strip()
    if not query:
        return {"results": []}

    r = requests.get(
        API_URL + "/search_by_name",
        params={"query": query},
        timeout=TIMEOUT,
    )
    r.raise_for_status()
    raw = r.json()

    # api_gateway сейчас возвращает просто массив
    results = []
    for a in raw:
        results.append(
            {
                "id": a["id"],
                "name": a["name"],
                "lat": float(a["lat"]),
                "lon": float(a["lon"]),
            }
        )

    return {"results": results}
