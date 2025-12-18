from typing import List, Tuple

from ..state import Airport
from .utils import haversine_km


AIRPORTS_DB: Tuple[dict, ...] = (
    {"icao": "UUDD", "name": "Домодедово", "lat": 55.409, "lon": 37.902},
    {"icao": "UUWW", "name": "Внуково", "lat": 55.597, "lon": 37.261},
    {"icao": "UUEE", "name": "Шереметьево", "lat": 55.973, "lon": 37.414},
    {"icao": "UUMO", "name": "Мячково", "lat": 55.558, "lon": 38.150},
    {"icao": "ULLI", "name": "Пулково", "lat": 59.799, "lon": 30.268},
    {"icao": "URSS", "name": "Сочи", "lat": 43.448, "lon": 39.956},
    {"icao": "UNOO", "name": "Омск Центральный", "lat": 54.967, "lon": 73.310},
    {"icao": "UHHH", "name": "Хабаровск Новый", "lat": 48.525, "lon": 135.188},
    {"icao": "EVRA", "name": "Рига", "lat": 56.923, "lon": 23.971},
    {"icao": "EFHK", "name": "Хельсинки-Вантаа", "lat": 60.317, "lon": 24.963},
)


def search_airports(lat: float, lon: float, radius_km: int) -> List[Airport]:
    """Return airports within radius sorted by distance."""
    candidates: List[Tuple[float, Airport]] = []
    for entry in AIRPORTS_DB:
        distance = haversine_km(lat, lon, entry["lat"], entry["lon"])
        if distance <= radius_km:
            candidates.append(
                (
                    distance,
                    Airport(
                        icao=entry["icao"],
                        name=entry["name"],
                        lat=entry["lat"],
                        lon=entry["lon"],
                        distance_km=distance,
                    ),
                )
            )

    candidates.sort(key=lambda item: item[0])
    return [item[1] for item in candidates]
