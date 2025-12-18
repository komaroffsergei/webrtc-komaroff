import requests
from src_llm_test.mcp_tools import mcp_tool

API = "http://127.0.0.1:8100/api"

ARTIFACTS = {}


@mcp_tool(
    description="Получает текущую позицию пользователя",
    provides=["current_position"]
)
def get_current_position():
    r = requests.get(f"{API}/pilot/location")
    r.raise_for_status()
    pos = r.json()
    ARTIFACTS["current_position"] = pos
    return True, {
        "status": "ok",
        "artifact_key": "current_position"
    }


@mcp_tool(
    description="Поиск ближайших открытых аэропортов",
    consumes=["current_position"],
    provides=["airports"],
    parameters={
        "radius_km": "Радиус поиска в километрах",
    }
)
def search_nearest_airports(radius_km: float):
    pos = ARTIFACTS["current_position"]
    r = requests.get(
        f"{API}/airports/nearest",
        params={
            "lat": pos["lat"],
            "lon": pos["lon"],
            "radius_km": radius_km,
            "status": "open"
        }
    )
    r.raise_for_status()
    res = r.json()["results"]
    ARTIFACTS["airports"] = res
    return True, {
        "status": "ok",
        "artifact_key": "airports",
        "count": len(res)
    }


@mcp_tool(
    description=(
        "Выбирает аэропорт с самой короткой взлётно-посадочной полосой "
        "из ранее найденных аэропортов."
    ),
    consumes=["airports"],
    provides=["airports"],
    parameters={
        "require_runway_status": (
            "Если указано, учитывать только ВПП с данным статусом: "
            "free, busy или closed"
        ),
        "surface": (
            "Если указано, учитывать только ВПП с данным материалом: "
            "concrete или asphalt"
        ),
    }
)
def select_airport_with_shortest_runway(
    require_runway_status: str | None = None,
    surface: str | None = None,
):
    selected = None
    shortest_length = None

    if ARTIFACTS.get("airports") is None:
        return True, {
            "status": "error",
            "message": "Необходимо сначала выполнить поиск аэродромов"
        }

    for airport in ARTIFACTS["airports"]:
        for runway in airport.get("runways", []):
            if require_runway_status and runway["status"] != require_runway_status:
                continue
            if surface and runway["surface"] != surface:
                continue

            length = runway["length_m"]

            if shortest_length is None or length < shortest_length:
                shortest_length = length
                selected = {
                    **airport,
                    "runways": [runway]
                }

    if not selected:
        return False, {
            "status": "error",
            "message": "Не найдено ВПП, подходящих под условия"
        }

    ARTIFACTS["airports"] = [selected]

    return False, {
        "status": "ok",
        "selected_airport_id": selected["id"],
        "shortest_runway_length_m": shortest_length
    }


@mcp_tool(
    description="Построение маршрута от текущей позиции до выбранного аэропорта",
    consumes=["current_position", "airports"],
    provides=["route"]
)
def build_route_to_first_airport():
    pos = ARTIFACTS["current_position"]
    airport = ARTIFACTS["airports"][0]

    r = requests.post(
        f"{API}/routes/build",
        params={
            "start_lat": pos["lat"],
            "start_lon": pos["lon"],
            "end_lat": airport["lat"],
            "end_lon": airport["lon"]
        }
    )
    r.raise_for_status()
    route = r.json()
    ARTIFACTS["route"] = route
    return False, route

