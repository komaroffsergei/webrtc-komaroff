import requests

from src_mcp_gateway.config_loader import load_settings

SETTINGS = load_settings()
API_URL = SETTINGS["services"]["weather_api"]
TIMEOUT = SETTINGS["network"]["timeout_seconds"]


def run(params):
    """
    Получить список погодных зон (циклонов).

    Вход:
      {}  (параметров нет)

    Выход:
      {
        "cyclones": [
          {
            "id": str,
            "name": str,
            "polygon": [[lon, lat], ...]
          }, ...
        ]
      }
    """
    r = requests.get(API_URL + "/cyclones", timeout=TIMEOUT)
    r.raise_for_status()
    data = r.json()

    cyclones = data.get("cyclones", [])
    norm = []
    for c in cyclones:
        norm.append(
            {
                "id": str(c["id"]),
                "name": str(c.get("name", "")),
                "polygon": c.get("polygon", []),
            }
        )

    return {"cyclones": norm}
