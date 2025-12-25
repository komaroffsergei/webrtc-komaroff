from typing import Tuple, Dict, Any, List

import requests

from src_agent.utils.mcp_tools import mcp_tool

API = "http://127.0.0.1:8100/api"

# =============================
# ARTIFACT STORAGE (per intent)
# =============================

ARTIFACTS: Dict[str, Any] = {}


def reset_artifacts():
    ARTIFACTS.clear()


# =============================
# TOOLS
# =============================


@mcp_tool(
    description=(''),
)
def no_tool_calls():
    return True, {
        "status": "error",
        "code": "NO_TOOL_CALLS",
        "message": "Необходимо вызвать инструмент"
    }

# @mcp_tool(
#     description=(
#             'Терминальный инструмент. Вызывается когда нет подходящего инструмента для удовлетворения запроса'
#     ),
# )
# def tool_does_not_exist():
#     return True, {
#       "status": "FAILED",
#       "error": "UNSUPPORTED_REQUEST",
#       "message": "Запрос не может быть выполнен доступными инструментами"
#     }

@mcp_tool(
    description=(
        "Терминальный инструмент. Возвращает финальный ответ пользователю. "
        "ДОЛЖЕН вызываться ТОЛЬКО один раз в конце выполнения. "
        "Аргумент artifact_keys — ОБЯЗАТЕЛЬНЫЙ массив строк, "
        "каждая строка — ключ ранее созданного артефакта. "
        "Одиночные значения, строки или объекты недопустимы."
    ),
    parameters={
        "artifact_keys": (
            "Array[string]. Список ключей артефактов, которые нужно включить "
            "в финальный ответ. Даже один ключ должен быть передан как массив."
        )
    }
)
def display_result(*, artifact_keys) -> Tuple[bool, Dict[str, Any]]:
    # --- normalization ---
    if isinstance(artifact_keys, str):
        artifact_keys = [artifact_keys]

    elif isinstance(artifact_keys, (tuple, set)):
        artifact_keys = list(artifact_keys)

    elif not isinstance(artifact_keys, list):
        raise ValueError(
            f"artifact_keys must be list[str], got {type(artifact_keys).__name__}"
        )

    if not artifact_keys:
        raise ValueError("artifact_keys must not be empty")

    # --- validation ---
    result = {}
    missing = []

    for key in artifact_keys:
        if not isinstance(key, str):
            raise ValueError(f"artifact key must be string, got {type(key).__name__}")

        if key not in ARTIFACTS:
            missing.append(key)
        else:
            result[key] = ARTIFACTS[key]

    if missing:
        raise RuntimeError(f"Artifacts not found: {missing}")

    return False, { # предполагаем что на этом цикл заканчивается
        "status": "ok",
        "result": result
    }


@mcp_tool(
    description="Получает текущую позицию пользователя",
    provides=["current_position"]
)
def get_current_position() -> Tuple[bool, Dict[str, Any]]:
    r = requests.get(f"{API}/pilot/location", timeout=10)
    r.raise_for_status()
    pos = r.json()

    ARTIFACTS["current_position"] = pos

    return True, {
        "status": "ok",
        "artifact_key": "current_position"
    }


@mcp_tool(
    description="Ищет ближайшие аэропорты в радиусе от текущей позиции",
    consumes=["current_position"],
    provides=["selected_airports"],
    parameters={
        "radius_km": "Радиус поиска в километрах"
    }
)
def search_nearest_airports(*, radius_km: int) -> Tuple[bool, Dict[str, Any]]:
    pos = ARTIFACTS.get("current_position")
    if not pos:
        return True, {
            "status": "error",
            "code": "NO_CURRENT_POSITION",
            "message": "Сначала нужно получить текущую позицию"
        }

    r = requests.get(
        f"{API}/airports/nearest",
        params={
            "lat": pos["lat"],
            "lon": pos["lon"],
            "radius_km": radius_km
        },
        timeout=10
    )
    r.raise_for_status()
    data = r.json()

    airports = data.get("results", [])
    ARTIFACTS["selected_airports"] = airports

    return True, {
        "status": "ok",
        "artifact_key": "selected_airports",
        "count": len(airports),
        "message": f"Найдено {len(airports)} ближайших аэродрома к заданным координатам"
    }


@mcp_tool(
    description="Выбирает аэропорт с самой короткой ВПП без учёта статуса",
    consumes=["selected_airports"],
    provides=["selected_airports"]
)
def select_airport_with_shortest_runway() -> Tuple[bool, Dict[str, Any]]:
    airports = ARTIFACTS.get("selected_airports")
    if not isinstance(airports, list):
        return True, {
            "status": "error",
            "message": "Ожидался массив аэропортов"
        }

    selected = None
    shortest = None

    for entry in airports:
        airport = entry if isinstance(entry, dict) else entry[0]
        runways = airport.get("runways", [])

        for rw in runways:
            length = rw.get("length_m")
            if not isinstance(length, (int, float)):
                continue

            if shortest is None or length < shortest:
                shortest = length
                selected = {**airport, "runways": [rw]}

    if not selected:
        return False, {
            "status": "error",
            "message": "Не удалось найти ВПП с корректной длиной"
        }

    ARTIFACTS["selected_airports"] = [selected]

    return True, {
        "status": "ok",
        "selected_airport_id": selected["id"],
        "shortest_runway_length_m": shortest
    }


@mcp_tool(
    description="Выбирает аэропорт с самой короткой ВПП с учётом статуса",
    consumes=["selected_airports"],
    provides=["selected_airports"],
    parameters={
        "require_runway_status": "Обязательный статус ВПП: free, busy или closed"
    }
)
def select_airport_with_shortest_runway_by_status(
    *,
    require_runway_status: str
) -> Tuple[bool, Dict[str, Any]]:
    airports = ARTIFACTS.get("selected_airports")
    if not airports:
        return True, {
            "status": "error",
            "message": "Необходимо сначала выполнить поиск аэродромов"
        }

    selected = None
    shortest = None

    for airport in airports:
        for rw in airport.get("runways", []):
            if rw.get("status") != require_runway_status:
                continue

            length = rw.get("length_m")
            if shortest is None or length < shortest:
                shortest = length
                selected = {**airport, "runways": [rw]}

    if not selected:
        return False, {
            "status": "error",
            "message": f"Не найдено ВПП со статусом {require_runway_status}"
        }

    ARTIFACTS["selected_airports"] = [selected]

    return True, {
        "status": "ok",
        "selected_airport_id": selected["id"],
        "shortest_runway_length_m": shortest,
        "runway_status": require_runway_status
    }


@mcp_tool(
    description="Выбирает аэропорт с самой короткой ВПП по типу покрытия",
    consumes=["selected_airports"],
    provides=["selected_airports"],
    parameters={
        "surface": "Материал покрытия ВПП: concrete или asphalt",
        "require_runway_status": "Учитывать только ВПП с данным статусом"
    }
)
def select_airport_with_shortest_runway_by_surface(
    *,
    surface: str,
    require_runway_status: str | None = None
) -> Tuple[bool, Dict[str, Any]]:
    airports = ARTIFACTS.get("selected_airports")
    if not airports:
        return True, {
            "status": "error",
            "message": "Необходимо сначала выполнить поиск аэродромов"
        }

    selected = None
    shortest = None

    for airport in airports:
        for rw in airport.get("runways", []):
            if rw.get("surface") != surface:
                continue
            if require_runway_status and rw.get("status") != require_runway_status:
                continue

            length = rw.get("length_m")
            if shortest is None or length < shortest:
                shortest = length
                selected = {**airport, "runways": [rw]}

    if not selected:
        return False, {
            "status": "error",
            "message": f"Не найдено ВПП с покрытием {surface}"
        }

    ARTIFACTS["selected_airports"] = [selected]

    return True, {
        "status": "ok",
        "selected_airport_id": selected["id"],
        "shortest_runway_length_m": shortest,
        "surface": surface
    }


@mcp_tool(
    description="Строит маршрут от текущей позиции до выбранного аэропорта",
    consumes=["current_position", "selected_airports"],
    provides=["route"]
)
def build_route_to_first_airport() -> Tuple[bool, Dict[str, Any]]:
    pos = ARTIFACTS.get("current_position")
    airports = ARTIFACTS.get("selected_airports")

    if not pos:
        return True, {
            "status": "error",
            "message": "Сначала нужно получить текущую позицию"
        }

    if not airports:
        return True, {
            "status": "error",
            "message": "Сначала нужно выбрать аэропорт"
        }

    airport = airports[0]

    route = {
        "from": pos,
        "to": {
            "id": airport["id"],
            "name": airport["name"],
            "lat": airport["lat"],
            "lon": airport["lon"]
        },
        "distance_km": 42.0  # заглушка как в Ruby
    }

    ARTIFACTS["route"] = route

    return True, {
        "status": "ok",
        "artifact_key": "route",
        "route": route
    }