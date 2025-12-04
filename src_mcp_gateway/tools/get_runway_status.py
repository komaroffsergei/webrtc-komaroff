import requests

from src_mcp_gateway.config_loader import load_settings

SETTINGS = load_settings()
API_URL = SETTINGS["services"]["runways_api"]
TIMEOUT = SETTINGS["network"]["timeout_seconds"]


def run(params):
    """
    Статусы ВПП для заданного аэропорта.

    Вход:
      { "airport_id": str }

    Выход:
      {
        "runways": [
          { "runway_id": str, "status": str },
          ...
        ]
      }
    """
    airport_id = str(params["airport_id"])

    url = f"{API_URL}/{airport_id}/runways"
    response = requests.get(url, timeout=TIMEOUT)
    response.raise_for_status()
    data = response.json()

    # api_gateway сейчас возвращает { "runways": [...] } или просто массив
    raw_runways = data.get("runways", data)

    runways = []
    for r in raw_runways:
        runways.append(
            {
                "runway_id": str(r["runway_id"]),
                "status": str(r["status"]),
            }
        )

    return {"runways": runways}
