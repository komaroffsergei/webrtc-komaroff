# src_langgraph/tools.py
from math import radians, sin, cos, asin, sqrt
from typing import List, Dict

from langchain_core.tools import tool


# -----------------------
# утилита расстояния
# -----------------------
def haversine_km(lat1, lon1, lat2, lon2):
    R = 6371.0
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat/2)**2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon/2)**2
    return R * 2 * asin(sqrt(a))


# -----------------------
# "база данных"
# -----------------------
AIRPORTS = [
    {"icao": "UUDD", "name": "Домодедово", "lat": 55.409, "lon": 37.902},
    {"icao": "UUWW", "name": "Внуково", "lat": 55.597, "lon": 37.261},
    {"icao": "UUEE", "name": "Шереметьево", "lat": 55.973, "lon": 37.414},
    {"icao": "UUMO", "name": "Мячково", "lat": 55.558, "lon": 38.150},
]

RUNWAYS = {
    "UUDD": [{"length_m": 3794, "free": True}],
    "UUWW": [{"length_m": 2706, "free": True}],
    "UUEE": [{"length_m": 3550, "free": True}],
    "UUMO": [{"length_m": 1400, "free": True}],
}


# -----------------------
# TOOLS
# -----------------------

@tool
def get_current_position() -> Dict[str, float]:
    """
    Получить текущую позицию пользователя.
    Используй, если пользователь не указал координаты.
    """
    pos = {"lat": 55.75, "lon": 37.61}
    print("[TOOL] get_current_position ->", pos)
    return pos


@tool
def search_airports(lat: float, lon: float, radius_km: int) -> List[Dict]:
    """
    Найти аэропорты в радиусе radius_km от точки lat/lon.
    """
    print(f"[TOOL] search_airports(lat={lat}, lon={lon}, radius={radius_km})")

    out = []
    for a in AIRPORTS:
        d = haversine_km(lat, lon, a["lat"], a["lon"])
        if d <= radius_km:
            out.append({**a, "distance_km": round(d, 1)})

    return sorted(out, key=lambda x: x["distance_km"])


@tool
def filter_airports_with_free_runways(airports: List[Dict]) -> List[Dict]:
    """
    Оставить только аэропорты со свободными ВПП.
    """
    print("[TOOL] filter_airports_with_free_runways")

    out = []
    for a in airports:
        rws = RUNWAYS.get(a["icao"], [])
        if any(r["free"] for r in rws):
            out.append(a)
    return out
