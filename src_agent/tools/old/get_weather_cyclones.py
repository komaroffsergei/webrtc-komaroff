import requests

from src_agent.settings import WEATHER_API_URL, TIMEOUT_SECONDS


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
    r = requests.get(WEATHER_API_URL + "/cyclones", timeout=TIMEOUT_SECONDS)
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
