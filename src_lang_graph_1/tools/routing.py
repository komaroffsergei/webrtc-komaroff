from typing import Iterable, Optional, Tuple

from ..state import Airport
from .utils import haversine_km, initial_bearing_deg


def build_direct_route(
    start_lat: float, start_lon: float, airports: Iterable[Airport]
) -> Tuple[Optional[Airport], Optional[str]]:
    """Pick the closest airport and describe a direct route."""
    best_airport: Optional[Airport] = None
    best_distance: Optional[float] = None

    for airport in airports:
        distance = haversine_km(start_lat, start_lon, airport.lat, airport.lon)
        if best_distance is None or distance < best_distance:
            best_distance = distance
            best_airport = airport

    if not best_airport or best_distance is None:
        return None, None

    bearing = initial_bearing_deg(start_lat, start_lon, best_airport.lat, best_airport.lon)
    summary = (
        f"Из координат ({start_lat:.2f}, {start_lon:.2f}) держите курс "
        f"{bearing:.0f}° около {best_distance:.0f} км до {best_airport.name} ({best_airport.icao})."
    )
    return best_airport, summary
