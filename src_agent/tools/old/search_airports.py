import requests

from src_agent.settings import AIRPORTS_API_URL, TIMEOUT_SECONDS


#
# API_URL = SETTINGS["services"]["airports_api"]
# TIMEOUT = SETTINGS["network"]["timeout_seconds"]


def run(params):
    """
    Поиск аэропортов в радиусе от заданной точки.

    Вход:
      {
        "lat": float,
        "lon": float,
        "radius_km": float
      }

    Выход:
      {
        "results": [
          {
            "id": str,
            "name": str,
            "lat": float,
            "lon": float,
            "distance_km": float
          }, ...
        ]
      }
    """
    lat = float(params["lat"])
    lon = float(params["lon"])
    radius_km = float(params["radius_km"])

    response = requests.get(

        AIRPORTS_API_URL,
        params={
            "radius_km": radius_km,
            "lat": lat,
            "lon": lon,
        },
        timeout=TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    data = response.json()

    # нормализуем структуру
    results = data.get("results", data)
    norm = []
    for a in results:
        norm.append(
            {
                "id": a["id"],
                "name": a["name"],
                "lat": float(a["lat"]),
                "lon": float(a["lon"]),
                "distance_km": float(a.get("distance_km", 0.0)),
            }
        )

    return {"results": norm}
