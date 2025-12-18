from typing import Iterable, List, Optional

from ..state import Airport, Runway

RUNWAY_DB = {
    "UUDD": [
        {"length_m": 3794, "surface": "бетон", "is_available": True},
        {"length_m": 3500, "surface": "бетон", "is_available": False},
    ],
    "UUEE": [
        {"length_m": 3550, "surface": "бетон", "is_available": True},
        {"length_m": 3200, "surface": "бетон", "is_available": True},
    ],
    "UUWW": [
        {"length_m": 3060, "surface": "бетон", "is_available": False},
        {"length_m": 2706, "surface": "бетон", "is_available": True},
    ],
    "UUMO": [
        {"length_m": 1400, "surface": "асфальт", "is_available": True},
    ],
    "ULLI": [
        {"length_m": 3782, "surface": "бетон", "is_available": True},
    ],
    "URSS": [
        {"length_m": 2960, "surface": "бетон", "is_available": True},
    ],
    "UNOO": [
        {"length_m": 2500, "surface": "бетон", "is_available": True},
    ],
    "UHHH": [
        {"length_m": 4000, "surface": "бетон", "is_available": False},
    ],
    "EVRA": [
        {"length_m": 3200, "surface": "бетон", "is_available": True},
    ],
    "EFHK": [
        {"length_m": 3500, "surface": "бетон", "is_available": True},
        {"length_m": 2900, "surface": "бетон", "is_available": True},
    ],
}


def filter_runways(
    airports: Iterable[Airport],
    *,
    min_length_m: Optional[int] = None,
    max_length_m: Optional[int] = None,
    require_available: bool = False,
) -> List[Runway]:
    results: List[Runway] = []
    for airport in airports:
        for runway in RUNWAY_DB.get(airport.icao, []):
            if min_length_m and runway["length_m"] < min_length_m:
                continue
            if max_length_m and runway["length_m"] > max_length_m:
                continue
            if require_available and not runway["is_available"]:
                continue
            results.append(
                Runway(
                    airport_icao=airport.icao,
                    length_m=runway["length_m"],
                    surface=runway["surface"],
                    is_available=runway["is_available"],
                )
            )
    return results
