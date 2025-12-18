import requests
from typing import Any

from src_llm_test.settings import (
    PILOT_API_URL,
    TIMEOUT_SECONDS,
    AIRPORTS_API_URL,
    RUNWAYS_API_URL,
)
from src_llm_test.mcp_tools import mcp_tool

ARTIFACTS = {}


@mcp_tool(description="Фатальная ошибка. Использовать только если дальнейшая работа невозможна.")
def display_error(msg: str):
    return False, f"Ошибка: {msg}"


@mcp_tool(description="Отображает ранее найденные аэропорты.")
def display_airports():
    if not ARTIFACTS.get("airports"):
        return False, "Аэропорты не найдены."

    lines = []
    for idx, a in enumerate(ARTIFACTS["airports"], start=1):
        lines.append(
            f"{idx}. {a.get('name', 'Без названия')} ({a.get('id', 'N/A')})\n"
            f"   Координаты: {float(a['lat']):.4f}, {float(a['lon']):.4f}\n"
            f"   Расстояние: {float(a.get('distance_km', 0.0)):.1f} км"
        )

    return False, "\n\n".join(lines)


@mcp_tool(description="Ищет аэропорты в заданном радиусе от точки.")
def search_airports(lat: float, lon: float, radius_km: float):
    response = requests.get(
        AIRPORTS_API_URL,
        params={"radius_km": radius_km, "lat": lat, "lon": lon},
        timeout=TIMEOUT_SECONDS,
    )
    response.raise_for_status()

    data = response.json()
    airports = data.get("results", [])

    ARTIFACTS["airports"] = airports

    if not airports:
        return False, "Аэропорты не найдены."

    return True, {
        "status": "ok",
        "artifact_key": "airports",
        "count": len(airports),
        "message": f"Найдено {len(airports)} аэропортов"
    }


@mcp_tool(description="Возвращает информацию о ВПП аэропорта.")
def runway_info(airport_id: str):
    r1 = requests.get(
        f"{RUNWAYS_API_URL}/{airport_id}/runways",
        timeout=TIMEOUT_SECONDS,
    )
    r1.raise_for_status()
    statuses = r1.json()["runways"]

    r2 = requests.get(
        f"{RUNWAYS_API_URL}/{airport_id}/runway_lengths",
        timeout=TIMEOUT_SECONDS,
    )
    r2.raise_for_status()
    lengths = r2.json()["runways"]

    length_map = {x["runway_id"]: x["length_m"] for x in lengths}

    final = []
    for s in statuses:
        rid = s["runway_id"]
        final.append(
            {
                "runway_id": rid,
                "status": s["status"],
                "length_m": length_map.get(rid, 0),
            }
        )

    ARTIFACTS.setdefault("runways", {})[airport_id] = final
    return True, {"runways": final}


@mcp_tool(description="Получает текущую гео-позицию пользователя.")
def get_current_position():
    r = requests.get(PILOT_API_URL, timeout=TIMEOUT_SECONDS)
    r.raise_for_status()
    data = r.json()

    ARTIFACTS["current_position"] = data
    return True, {
        "status": "ok",
        "artifact_key": "current_position",
        "message": "Текущая позиция получена"
    }


@mcp_tool(description="Поиск аэропорта по названию или его части.")
def get_airport_by_name(query: str):
    query = query.strip()
    if not query:
        return False, []

    r = requests.get(
        AIRPORTS_API_URL + "/search_by_name",
        params={"query": query},
        timeout=TIMEOUT_SECONDS,
    )
    r.raise_for_status()

    return False, r.json()


@mcp_tool(description="Фильтрует и агрегирует ранее найденные аэропорты.")
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

        free = [r for r in runways if r["status"] == "free"]
        if require_free_runway and not free:
            continue

        max_len = max((r["length_m"] for r in free), default=0)
        if min_runway_length_m and max_len < min_runway_length_m:
            continue

        results.append(
            {
                "id": aid,
                "name": airport.get("name"),
                "distance_km": airport.get("distance_km"),
                "max_free_runway_length_m": max_len,
            }
        )

    if sort_by == "max_free_runway_length":
        results.sort(key=lambda x: x["max_free_runway_length_m"], reverse=True)
    elif sort_by == "distance_km":
        results.sort(key=lambda x: x["distance_km"])

    if limit:
        results = results[:limit]

    return False, results
