import requests

from src_mcp_gateway.config_loader import load_settings

SETTINGS = load_settings()
API_URL = SETTINGS["services"]["routes_api"]
TIMEOUT = SETTINGS["network"]["timeout_seconds"]


def run(params):
    """
    Поиск одного ближайшего маршрута от точки до аэропорта.

    Вход:
      {
        "lat": float,
        "lon": float,
        "radius_km": float | null,
        "require_free_runway": bool
      }

    Выход:
      {
        "fallback": bool,
        "reason": str | null,
        "distance_km": float | null,
        "airport": {id, name, lat, lon} | null,
        "geometry": [[lon, lat], ...] | null
      }
    """
    lat = float(params["lat"])
    lon = float(params["lon"])
    radius_km = params.get("radius_km")
    require_free_runway = bool(params.get("require_free_runway", False))

    query = {
        "lat": lat,
        "lon": lon,
        "require_free_runway": require_free_runway,
    }
    if radius_km is not None:
        query["radius_km"] = float(radius_km)

    response = requests.get(API_URL, params=query, timeout=TIMEOUT)
    response.raise_for_status()
    data = response.json()

    # api_gateway возвращает:
    # {
    #   "fallback": bool,
    #   "distance_km": float,
    #   "airport": {...},
    #   "geometry": [...]
    # }
    return {
        "fallback": bool(data.get("fallback", False)),
        "reason": data.get("reason"),
        "distance_km": float(data["distance_km"]) if "distance_km" in data else None,
        "airport": data.get("airport"),
        "geometry": data.get("geometry"),
    }
