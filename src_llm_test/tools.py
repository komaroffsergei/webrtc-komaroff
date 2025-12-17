import json
from typing import Dict, Any

import requests

from src_llm_test.settings import PILOT_API_URL, TIMEOUT_SECONDS, AIRPORTS_API_URL, RUNWAYS_API_URL
ARTIFACTS = {}

def display_error(msg):
    return f'Error: {msg}'
def display_airports():
    if 'airports' not in ARTIFACTS or not ARTIFACTS['airports']:
        return "Аэропорты не найдены."

    lines = []
    for idx, a in enumerate(ARTIFACTS['airports'], start=1):
        line = (
            f"{idx}. {a.get('name', 'Без названия')} "
            f"({a.get('id', 'N/A')})\n"
            f"   Координаты: {float(a['lat']):.4f}, {float(a['lon']):.4f}\n"
            f"   Расстояние: {float(a.get('distance_km', 0.0)):.1f} км"
        )
        lines.append(line)

    return (False, "\n\n".join(lines))



def search_airports(lat: float, lon: float, radius_km: float):
    if lat is None or lon is None:
        return {
            "error": {
                "code": "MISSING_PARAMETER",
                "parameter": "lat|lon",
                "message": "lat  and lon is required"
            }
        }

    if radius_km is None:
        return {
            "error": {
                "code": "MISSING_PARAMETER",
                "parameter": "radius_km",
                "message": "radius_km is required"
            }
        }

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
    airports = response.json()

    # нормализуем структуру
    ARTIFACTS['airports'] = airports.get("results", [])
    # results = data.get("results", data)
    # norm = []
    # for a in results:
    #     norm.append(
    #         {
    #             "id": a["id"],
    #             "name": a["name"],
    #             "lat": float(a["lat"]),
    #             "lon": float(a["lon"]),
    #             "distance_km": float(a.get("distance_km", 0.0)),
    #         }
    #     )

    if airports is None:
        return (False, "Не получены аэропорты. Инструмент отработал с ошибкой. Выведи пользователю сообщение об ошибке")
    elif len(airports) == 0:
        return (False, "Не найдено ни одного аэропорта. Инструмент вернул пустой результат. Выведи пользователю сообщение об ошибке")
    else:
        return (True, f"Найдено {len(airports)} аэропортов. Результат сохранен в хранилище. Инструмент отработал успешно")



def get_runway_info(airport_id):
    if airport_id is None:
        return {
            "error": {
                "code": "MISSING_PARAMETER",
                "parameter": "airport_id",
                "message": "airport_id is required"
            }
        }

    r1 = requests.get(f"{RUNWAYS_API_URL}/{airport_id}/runways", timeout=TIMEOUT_SECONDS)
    r1.raise_for_status()
    statuses = r1.json()["runways"]

    # Second service or same service endpoint
    r2 = requests.get(f"{RUNWAYS_API_URL}/{airport_id}/runway_lengths", timeout=TIMEOUT_SECONDS)
    r2.raise_for_status()
    lengths = r2.json()["runways"]

    # merge
    length_map = {x["runway_id"]: x["length_m"] for x in lengths}

    final = []
    for s in statuses:
        rid = s["runway_id"]
        final.append({
            "runway_id": rid,
            "status": s["status"],
            "length_m": length_map.get(rid, 0)
        })

    return {"runways": final}

def get_current_position():
    """
    Текущая позиция "пилота" / исходной точки.

    Вход:
      {}  (без параметров)

    Выход:
      { "lat": float, "lon": float }
    """
    r = requests.get(PILOT_API_URL, timeout=TIMEOUT_SECONDS)
    r.raise_for_status()
    data = r.json()
    ARTIFACTS['current_position'] = data

    return (True, f"Инструмент вернул координаты lat:{data['lat']}, lon: {data['lon']}")


def get_airport_by_name(params):
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
        AIRPORTS_API_URL + "/search_by_name",
        params={"query": query},
        timeout=TIMEOUT_SECONDS,
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


def query_airports(
    require_free_runway: bool = False,
    min_runway_length_m: int | None = None,
    sort_by: str | None = None,
    limit: int | None = None,
):
    results = []

    for airport in ARTIFACTS.get("airports", []):
        aid = airport["id"]
        runways = ARTIFACTS.get("runways", {}).get(aid, [])

        free_runways = [r for r in runways if r.get("status") == "free"]

        if require_free_runway and not free_runways:
            continue

        max_free_len = max(
            (r["length_m"] for r in free_runways),
            default=0
        )

        if min_runway_length_m and max_free_len < min_runway_length_m:
            continue

        results.append({
            "id": aid,
            "name": airport.get("name"),
            "distance_km": airport.get("distance_km"),
            "max_free_runway_length_m": max_free_len,
        })

    if sort_by == "max_free_runway_length":
        results.sort(key=lambda x: x["max_free_runway_length_m"], reverse=True)
    elif sort_by == "distance_km":
        results.sort(key=lambda x: x["distance_km"])

    if limit:
        results = results[:limit]

    return results

