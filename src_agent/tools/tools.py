import os
import re
import math
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Tuple, Dict, Any

import requests

from src_agent.utils.mcp_tools import mcp_tool
from src_agent.settings import (
    TOOL_ASK_USER_INPUT_DESCRIPTION,
    TOOL_ASK_USER_INPUT_MESSAGE_PARAM,
    TOOL_FLIGHT_STATUS_DESCRIPTION,
    TOOL_FLIGHT_STATUS_FLIGHT_NUMBER_PARAM,
    TOOL_FLIGHT_STATUS_SURNAME_PARAM,
)

API = os.getenv("API_URL", "http://127.0.0.1:8100/api")
FLIGHTS_API_URL = os.getenv("FLIGHTS_API_URL", "http://127.0.0.1:8100/api/flights/status")

# Контекст выполнения tools:
# - `_TOOL_STATE` хранит текущий conversation state (state) для записи/чтения артефактов
# - `_TOOL_SCENARIO_ID` хранит id сценария, чтобы изолировать артефакты по сценариям
#
# Это реализовано через ContextVar, потому что сценарии асинхронные и tool-вызовы могут
# происходить глубоко внутри call stack (включая вложенные функции).
_TOOL_STATE: ContextVar[Dict[str, Any] | None] = ContextVar("_TOOL_STATE", default=None)
_TOOL_SCENARIO_ID: ContextVar[str | None] = ContextVar("_TOOL_SCENARIO_ID", default=None)


@contextmanager
def tool_context(state: Dict[str, Any], scenario_id: str):
    """
    Установить контекст выполнения tools для конкретного сценария.

    Почти все tools складывают результаты в `state["scenario_artifacts"][scenario_id]` и возвращают `artifact_key`.
    Этот контекст обязателен, иначе put/get артефактов не знают, куда писать.
    """
    token_state = _TOOL_STATE.set(state)
    token_scenario = _TOOL_SCENARIO_ID.set(scenario_id)
    try:
        yield
    finally:
        _TOOL_SCENARIO_ID.reset(token_scenario)
        _TOOL_STATE.reset(token_state)


def _require_context() -> tuple[Dict[str, Any], str]:
    # Защита от случайных вызовов tool без `tool_context(...)`.
    state = _TOOL_STATE.get()
    scenario_id = _TOOL_SCENARIO_ID.get()
    if state is None or not scenario_id:
        raise RuntimeError("Tool context is not set (state/scenario_id missing)")
    return state, scenario_id


def _scenario_artifacts(state: Dict[str, Any], scenario_id: str) -> Dict[str, Any]:
    # Артефакты изолированы по scenario_id, чтобы сценарии не “делились” промежуточными результатами.
    scenarios = state.setdefault("scenario_artifacts", {})
    scenario_store = scenarios.get(scenario_id)
    if scenario_store is None:
        scenario_store = {}
        scenarios[scenario_id] = scenario_store
    if not isinstance(scenario_store, dict):
        raise RuntimeError("Invalid scenario_artifacts storage type")
    return scenario_store


def _artifact_key(label: str) -> str:
    # Нормализуем ключ артефакта: "{scenario_id}.tool.{label}".
    _, scenario_id = _require_context()
    return f"{scenario_id}.tool.{label}"


def put_artifact(label: str, value: Any) -> str:
    # Записать артефакт в storage текущего сценария и вернуть его ключ.
    state, scenario_id = _require_context()
    key = _artifact_key(label)
    store = _scenario_artifacts(state, scenario_id)
    store[key] = value
    return key


def get_artifact(label: str) -> Any:
    # Получить артефакт по label (в рамках текущего сценария).
    state, scenario_id = _require_context()
    key = _artifact_key(label)
    store = _scenario_artifacts(state, scenario_id)
    if key not in store:
        raise RuntimeError(f"Artifact not found in scenario scope: {key}")
    return store[key]


def get_artifact_by_key(key: str) -> Any:
    # Получить артефакт по “абсолютному” ключу, но всё ещё в рамках текущего scenario_id.
    # Это сознательное ограничение: сценарии не должны читать артефакты друг друга неявно.
    state, scenario_id = _require_context()
    store = _scenario_artifacts(state, scenario_id)
    if key not in store:
        raise RuntimeError(f"Artifact not found in scenario scope: {key}")
    return store[key]


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
        "message": "A tool call is required."
    }


@mcp_tool(
    description=TOOL_ASK_USER_INPUT_DESCRIPTION,
    provides=["user_request"],
    parameters={
        "message": TOOL_ASK_USER_INPUT_MESSAGE_PARAM
    },
    client_handler="ASK_USER_INPUT"
)
def ask_user_input(*, message: str) -> Tuple[bool, Dict[str, Any]]:
    if not isinstance(message, str) or not message.strip():
        return True, {
            "status": "error",
            "message": "message must be a non-empty string",
        }

    key = put_artifact("ask_user_input", {"message": message})

    return False, {
        "status": "ok",
        "artifact_key": key,
        "message": message,
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
    description=TOOL_FLIGHT_STATUS_DESCRIPTION,
    provides=["flight_status"],
    parameters={
        "flight_number": TOOL_FLIGHT_STATUS_FLIGHT_NUMBER_PARAM,
        "surname": TOOL_FLIGHT_STATUS_SURNAME_PARAM,
    },
)
def get_flight_status(*, flight_number: str | None = None, surname: str | None = None) -> Tuple[bool, Dict[str, Any]]:
    params: dict[str, object] = {}
    if flight_number is not None:
        params["flight_number"] = flight_number
    if surname is not None:
        params["surname"] = surname
    r = requests.get(
        FLIGHTS_API_URL,
        params=params,
        timeout=10,
    )
    r.raise_for_status()
    data = r.json()

    key = put_artifact("flight_status", data)

    return True, {
        "status": "ok",
        "artifact_key": key,
    }


@mcp_tool(
    description="Получает текущую позицию пользователя",
    provides=["current_position"],
    client_handler="SET_POSITION"
)
def get_current_position() -> Tuple[bool, Dict[str, Any]]:
    r = requests.get(f"{API}/pilot/location", timeout=10)
    r.raise_for_status()
    pos = r.json()

    lat = pos.get("lat")
    lon = pos.get("lon")
    if not isinstance(lat, (int, float)) or not isinstance(lon, (int, float)):
        return True, {
            "status": "error",
            "message": "Invalid position payload",
        }

    key = put_artifact("current_position", {"data": {"current_position": {"lat": float(lat), "lon": float(lon)}}})

    return True, {
        "status": "ok",
        "artifact_key": key,
        "lat": float(lat),
        "lon": float(lon),
    }


@mcp_tool(
    description="Получает полный список аэропортов из мок-API (airports.json).",
    provides=["airports_list"],
    client_handler="SET_AIRPORTS",
)
def list_airports() -> Tuple[bool, Dict[str, Any]]:
    r = requests.get(f"{API}/airports/list", timeout=10)
    r.raise_for_status()
    data = r.json()
    airports = data.get("results", [])
    key = put_artifact("airports_list", {"data": {"airports": airports}})
    return True, {
        "status": "ok",
        "artifact_key": key,
        "count": len(airports) if isinstance(airports, list) else None,
    }


@mcp_tool(
    description="Строит маршрут по дуге большого круга между двумя точками, используя мок-API.",
    provides=["route_geometry"],
    parameters={
        "start_lat": "Начальная широта",
        "start_lon": "Начальная долгота",
        "end_lat": "Конечная широта",
        "end_lon": "Конечная долгота",
    },
    client_handler="BUILD_ROUTE",
)
def build_route(*, start_lat: float, start_lon: float, end_lat: float, end_lon: float) -> Tuple[bool, Dict[str, Any]]:
    r = requests.post(
        f"{API}/routes/build",
        params={"start_lat": start_lat, "start_lon": start_lon, "end_lat": end_lat, "end_lon": end_lon},
        timeout=10,
    )
    r.raise_for_status()
    data = r.json()
    geometry = data.get("geometry")
    distance = data.get("distance_km")
    key = put_artifact("route_geometry", {"data": {"geometry": geometry, "distance_km": distance}})
    return True, {
        "status": "ok",
        "artifact_key": key,
        "distance_km": distance,
    }


@mcp_tool(
    description="Определяет аэропорт из произвольного пользовательского текста с помощью поиска в мок-API.",
    provides=["resolved_airport"],
    parameters={
        "user_text": "Пользовательский текст, содержащий название или код аэропорта."
    },
)
def resolve_airport(*, user_text: str) -> Tuple[bool, Dict[str, Any]]:
    if not isinstance(user_text, str) or not user_text.strip():
        return True, {"status": "error", "message": "user_text must be a non-empty string"}

    text = user_text.strip()
    code_match = None
    m = re.search(r"\\b([A-Za-z]{3,4})\\b", text)
    if m:
        code_match = m.group(1).upper()

    candidates: list[str] = []
    candidates.append(text)
    if code_match:
        candidates.append(code_match)
    cleaned = re.sub(r"\\b(airport|airports|aerodrome|aerodromes)\\b", "", text, flags=re.IGNORECASE).strip()
    cleaned = re.sub(r"\\b(аэропорт|аэропорты|аэродром|аэродромы)\\b", "", cleaned, flags=re.IGNORECASE).strip()
    cleaned = re.sub(r"^(до|от|из|в|к)\\b", "", cleaned, flags=re.IGNORECASE).strip()
    cleaned = re.sub(r"\\s+", " ", cleaned).strip()
    if cleaned and cleaned not in candidates:
        candidates.append(cleaned)

    seen: dict[str, dict] = {}
    for q in candidates:
        if not q:
            continue
        r = requests.get(f"{API}/airports/search_by_name", params={"query": q}, timeout=10)
        r.raise_for_status()
        data = r.json()
        results = data.get("results", [])
        if not isinstance(results, list):
            continue
        for a in results:
            if not isinstance(a, dict):
                continue
            aid = str(a.get("id") or "")
            acode = str(a.get("code") or "")
            key = aid or acode
            if not key:
                continue
            if key not in seen:
                seen[key] = a

    options = list(seen.values())
    slim = [
        {
            "id": a.get("id"),
            "code": a.get("code"),
            "name": a.get("name"),
            "lat": a.get("lat"),
            "lon": a.get("lon"),
            "status": a.get("status"),
        }
        for a in options
    ]

    if code_match:
        for a in slim:
            if str(a.get("code") or "").upper() == code_match or str(a.get("id") or "").upper() == code_match:
                put_artifact("resolved_airport", {"data": {"status": "ok", "airport": a}})
                return True, {"status": "ok", "airport": a}

    if len(slim) == 1:
        put_artifact("resolved_airport", {"data": {"status": "ok", "airport": slim[0]}})
        return True, {"status": "ok", "airport": slim[0]}
    if len(slim) > 1:
        put_artifact("resolved_airport", {"data": {"status": "ambiguous", "options": slim}})
        return True, {"status": "ambiguous", "options": slim}

    put_artifact("resolved_airport", {"data": {"status": "not_found"}})
    return True, {"status": "not_found"}

@mcp_tool(
    description="Загружает все аэропорты из мок-API (airports.json).",
    provides=["airports_all"],
    client_handler="SHOW_AIRPORTS",
)
def get_all_airports() -> Tuple[bool, Dict[str, Any]]:
    r = requests.get(f"{API}/airports/list", timeout=10)
    r.raise_for_status()
    data = r.json()
    airports = data.get("results", [])
    key = put_artifact("airports_all", {"data": {"airports": airports}})
    return True, {
        "status": "ok",
        "artifact_key": key,
        "count": len(airports) if isinstance(airports, list) else None,
    }


@mcp_tool(
    description="Загружает открытые аэропорты из мок-API (airports.json).",
    provides=["airports_open"],
    client_handler="SHOW_AIRPORTS",
)
def get_open_airports() -> Tuple[bool, Dict[str, Any]]:
    r = requests.get(f"{API}/airports/list", params={"status": "open"}, timeout=10)
    r.raise_for_status()
    data = r.json()
    airports = data.get("results", [])
    key = put_artifact("airports_open", {"data": {"airports": airports}})
    return True, {
        "status": "ok",
        "artifact_key": key,
        "count": len(airports) if isinstance(airports, list) else None,
    }


@mcp_tool(
    description="Загружает закрытые аэропорты из мок-API (airports.json).",
    provides=["airports_closed"],
    client_handler="SHOW_AIRPORTS",
)
def get_closed_airports() -> Tuple[bool, Dict[str, Any]]:
    r = requests.get(f"{API}/airports/list", params={"status": "closed"}, timeout=10)
    r.raise_for_status()
    data = r.json()
    airports = data.get("results", [])
    key = put_artifact("airports_closed", {"data": {"airports": airports}})
    return True, {
        "status": "ok",
        "artifact_key": key,
        "count": len(airports) if isinstance(airports, list) else None,
    }


@mcp_tool(
    description="Ищет аэропорты по названию или коду с использованием мок-API (airports.json).",
    provides=["airports_search"],
    parameters={
        "query": "Поисковый запрос (название или код)."
    },
    client_handler="SHOW_AIRPORTS",
)
def search_airports_by_name_or_code(*, query: str) -> Tuple[bool, Dict[str, Any]]:
    if not isinstance(query, str) or not query.strip():
        return True, {"status": "error", "message": "query must be a non-empty string"}
    q = query.strip()
    r = requests.get(f"{API}/airports/search_by_name", params={"query": q}, timeout=10)
    r.raise_for_status()
    data = r.json()
    airports = data.get("results", [])
    key = put_artifact("airports_search", {"data": {"airports": airports, "query": q}})
    return True, {
        "status": "ok",
        "artifact_key": key,
        "count": len(airports) if isinstance(airports, list) else None,
    }


@mcp_tool(
    description="Ищет ближайшие аэропорты в радиусе от текущей позиции",
    consumes=["current_position"],
    provides=["selected_airports"],
    parameters={
        "radius_km": "Радиус поиска в километрах"
    },
    client_handler="SHOW_AIRPORTS"
)
def search_nearest_airports(*, radius_km: int) -> Tuple[bool, Dict[str, Any]]:
    try:
        stored = get_artifact("current_position")
    except RuntimeError:
        return True, {
            "status": "error",
            "code": "NO_CURRENT_POSITION",
            "message": "Current position is required. Call get_current_position first.",
        }

    pos = (stored.get("data") or {}).get("current_position") if isinstance(stored, dict) else None
    if not isinstance(pos, dict):
        return True, {
            "status": "error",
            "code": "INVALID_CURRENT_POSITION",
            "message": "Current position payload is invalid.",
        }

    r = requests.get(
        f"{API}/airports/nearest",
        params={
            "lat": pos.get("lat"),
            "lon": pos.get("lon"),
            "radius_km": radius_km
        },
        timeout=10
    )
    r.raise_for_status()
    data = r.json()

    airports = data.get("results", [])
    key = put_artifact("nearest_airports", {"data": {"airports": airports, "radius_km": radius_km}})

    return True, {
        "status": "ok",
        "artifact_key": key,
        "count": len(airports),
        "message": f"Found {len(airports)} airports within {radius_km} km.",
    }


def _haversine_km(*, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2.0) ** 2
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2.0) ** 2
    )
    return 2.0 * r * math.asin(math.sqrt(a))


@mcp_tool(
    description="Выбирает один аэропорт по расстоянию от текущей позиции (ближайший или самый дальний).",
    consumes=["current_position"],
    provides=["airport_by_distance"],
    parameters={
        "mode": "Либо 'nearest', либо 'farthest'."
    },
)
def find_airport_by_distance(*, mode: str) -> Tuple[bool, Dict[str, Any]]:
    stored = get_artifact("current_position")
    pos = (stored["data"] or {})["current_position"]
    lat = float(pos["lat"])
    lon = float(pos["lon"])

    r = requests.get(f"{API}/airports/list", timeout=10)
    r.raise_for_status()
    airports = r.json()["results"]

    key_fn = lambda a: _haversine_km(lat1=lat, lon1=lon, lat2=float(a["lat"]), lon2=float(a["lon"]))
    selected = min(airports, key=key_fn) if mode == "nearest" else max(airports, key=key_fn)
    distance_km = round(key_fn(selected), 2)

    key = put_artifact("airport_by_distance", {"data": {"airport": selected, "distance_km": distance_km, "mode": mode}})
    return True, {"status": "ok", "artifact_key": key, "airport": selected, "distance_km": distance_km}


@mcp_tool(
    description="Выбирает аэропорт с самой короткой ВПП без учёта статуса",
    consumes=["selected_airports"],
    provides=["selected_airports"],
    client_handler="SHOW_AIRPORTS"
)
def select_airport_with_shortest_runway() -> Tuple[bool, Dict[str, Any]]:
    try:
        stored = get_artifact("nearest_airports")
        airports = (stored.get("data") or {}).get("airports") if isinstance(stored, dict) else None
    except RuntimeError:
        airports = None
    if not isinstance(airports, list):
        return True, {
            "status": "error",
            "message": "Expected a list of airports in scenario artifacts.",
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
            "message": "No runway with a valid length was found.",
        }

    key = put_artifact("selected_airport_shortest_runway", {"data": {"airports": [selected]}})

    return True, {
        "status": "ok",
        "artifact_key": key,
        "selected_airport_id": selected["id"],
        "shortest_runway_length_m": shortest
    }


@mcp_tool(
    description="Выбирает аэропорт с самой короткой ВПП с учётом статуса",
    consumes=["selected_airports"],
    provides=["selected_airports"],
    parameters={
        "require_runway_status": "Обязательный статус ВПП: free, busy или closed"
    },
    client_handler="SHOW_AIRPORTS"
)
def select_airport_with_shortest_runway_by_status(
    *,
    require_runway_status: str
) -> Tuple[bool, Dict[str, Any]]:
    try:
        stored = get_artifact("nearest_airports")
        airports = (stored.get("data") or {}).get("airports") if isinstance(stored, dict) else None
    except RuntimeError:
        airports = None
    if not isinstance(airports, list):
        return True, {
            "status": "error",
            "message": "Nearest airports are not available in scenario artifacts.",
        }

    selected = None
    shortest = None

    for entry in airports:
        airport = entry if isinstance(entry, dict) else entry[0]
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
            "message": f"No runway found with status={require_runway_status}.",
        }

    key = put_artifact(
        "selected_airport_shortest_runway_by_status",
        {"data": {"airports": [selected]}},
    )

    return True, {
        "status": "ok",
        "artifact_key": key,
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
    },
    client_handler="SHOW_AIRPORTS"
)
def select_airport_with_shortest_runway_by_surface(
    *,
    surface: str,
    require_runway_status: str | None = None
) -> Tuple[bool, Dict[str, Any]]:
    try:
        stored = get_artifact("nearest_airports")
        airports = (stored.get("data") or {}).get("airports") if isinstance(stored, dict) else None
    except RuntimeError:
        airports = None
    if not isinstance(airports, list):
        return True, {
            "status": "error",
            "message": "Nearest airports are not available in scenario artifacts.",
        }

    selected = None
    shortest = None

    for entry in airports:
        airport = entry if isinstance(entry, dict) else entry[0]
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
            "message": f"No runway found with surface={surface}.",
        }

    key = put_artifact(
        "selected_airport_shortest_runway_by_surface",
        {"data": {"airports": [selected]}},
    )

    return True, {
        "status": "ok",
        "artifact_key": key,
        "selected_airport_id": selected["id"],
        "shortest_runway_length_m": shortest,
        "surface": surface
    }


@mcp_tool(
    description="Строит маршрут от текущей позиции до выбранного аэропорта",
    consumes=["current_position", "selected_airports"],
    provides=["route"],
    client_handler="BUILD_ROUTE"
)
def build_route_to_first_airport() -> Tuple[bool, Dict[str, Any]]:
    try:
        pos = get_artifact("current_position")
    except RuntimeError:
        pos = None
    try:
        stored = get_artifact("selected_airport_shortest_runway")
        airports = (stored.get("data") or {}).get("airports") if isinstance(stored, dict) else None
    except RuntimeError:
        airports = None

    if not pos:
        return True, {
            "status": "error",
            "message": "Current position is required. Call get_current_position first.",
        }

    if not airports:
        return True, {
            "status": "error",
            "message": "A selected airport is required. Call select_airport_with_shortest_runway first.",
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

    key = put_artifact("route_to_first_airport", route)

    return True, {
        "status": "ok",
        "artifact_key": key,
        "route": route
    }
