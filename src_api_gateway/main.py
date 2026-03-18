import json
import os
import asyncio
import math
from uuid import uuid4
from typing import Optional

import uvicorn
from fastapi import FastAPI, Query
from fastapi.responses import JSONResponse

from nats.aio.client import Client as NATS
from nats.aio.msg import Msg

from src_shared.contracts import ErrorInfo, ToolCallRequest, ToolCallResponse, now_ts_ms

app = FastAPI(title="Mock Aviation API")

BASE_DIR = os.path.dirname(__file__)
DATA_FILE = os.path.join(BASE_DIR, "data", "airports.json")

API_PORT = int(os.getenv("API_PORT", "8100"))
API_HOST = os.getenv("API_HOST", "0.0.0.0")
NATS_URL = os.getenv("NATS_URL", "nats://localhost:4222")
NATS_TOOLS_PREFIX = os.getenv("NATS_TOOLS_PREFIX", "nats.tools.")

with open(DATA_FILE, "r", encoding="utf-8") as f:
    AIRPORTS = json.load(f)

CITY_COORDS: dict[str, tuple[float, float]] = {
    "moscow": (55.7558, 37.6173),
    "saint petersburg": (59.9343, 30.3351),
    "st petersburg": (59.9343, 30.3351),
    "amsterdam": (52.3676, 4.9041),
}

FLIGHTS: list[dict[str, str]] = [
    {
        "flight_number": "SU123",
        "last_name": "Иванов",
        "status": "ON_TIME",
        "from": "SVO",
        "to": "AMS",
        "departure_time": "2026-01-14T12:30:00Z",
        "arrival_time": "2026-01-14T15:10:00Z",
        "gate": "A12",
        "terminal": "C",
    },
    {
        "flight_number": "S123",
        "last_name": "Петров",
        "status": "DELAYED",
        "from": "DME",
        "to": "LED",
        "departure_time": "2026-01-14T09:10:00Z",
        "arrival_time": "2026-01-14T10:35:00Z",
        "gate": "B07",
        "terminal": "B",
    },
]


# -------------------------
# helpers
# -------------------------
def haversine(lat1, lon1, lat2, lon2):
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(dlon / 2) ** 2
    )
    return 2 * R * math.asin(math.sqrt(a))

def _to_vec(lat: float, lon: float) -> tuple[float, float, float]:
    lat_r = math.radians(lat)
    lon_r = math.radians(lon)
    x = math.cos(lat_r) * math.cos(lon_r)
    y = math.cos(lat_r) * math.sin(lon_r)
    z = math.sin(lat_r)
    return x, y, z


def _normalize(v: tuple[float, float, float]) -> tuple[float, float, float]:
    x, y, z = v
    mag = math.sqrt(x * x + y * y + z * z)
    if mag == 0.0:
        return 0.0, 0.0, 0.0
    return x / mag, y / mag, z / mag


def _dot(a: tuple[float, float, float], b: tuple[float, float, float]) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _from_vec(v: tuple[float, float, float]) -> tuple[float, float]:
    x, y, z = v
    lat = math.degrees(math.asin(max(-1.0, min(1.0, z))))
    lon = math.degrees(math.atan2(y, x))
    return lat, lon


def great_circle_geometry(
    *,
    start_lat: float,
    start_lon: float,
    end_lat: float,
    end_lon: float,
    points: int = 64,
) -> list[list[float]]:
    if points < 2:
        points = 2

    v0 = _normalize(_to_vec(start_lat, start_lon))
    v1 = _normalize(_to_vec(end_lat, end_lon))
    d = max(-1.0, min(1.0, _dot(v0, v1)))
    omega = math.acos(d)
    if omega < 1e-9:
        return [[start_lon, start_lat], [end_lon, end_lat]]

    sin_omega = math.sin(omega)
    if abs(sin_omega) < 1e-12:
        return [[start_lon, start_lat], [end_lon, end_lat]]

    coords: list[list[float]] = []
    for i in range(points):
        t = i / (points - 1)
        a = math.sin((1.0 - t) * omega) / sin_omega
        b = math.sin(t * omega) / sin_omega
        v = _normalize((a * v0[0] + b * v1[0], a * v0[1] + b * v1[1], a * v0[2] + b * v1[2]))
        lat, lon = _from_vec(v)
        coords.append([lon, lat])
    return coords


def _airport_matches_query(airport: dict, query: str) -> bool:
    q = (query or "").strip().lower()
    if not q:
        return False
    for key in ("name", "code", "id"):
        v = airport.get(key)
        if isinstance(v, str) and q in v.lower():
            return True
    aliases = airport.get("aliases")
    if isinstance(aliases, list):
        for a in aliases:
            if isinstance(a, str) and q in a.lower():
                return True
    return False


def _normalize_city(value: str) -> str:
    v = (value or "").strip().lower()
    if not v:
        return ""
    # Minimal transliteration support for demo UI prompts.
    if "моск" in v:
        return "moscow"
    if "петер" in v or "питер" in v:
        return "saint petersburg"
    return v


def _tool_search_airports_nearby(*, city: str, radius_km: float) -> dict:
    key = _normalize_city(city)
    coords = CITY_COORDS.get(key)
    if not coords:
        return {"error": {"code": "unknown_city", "message": f"Unknown city: {city}"}}
    lat, lon = coords
    res = []
    for a in AIRPORTS:
        dist = haversine(lat, lon, a["lat"], a["lon"])
        if dist <= float(radius_km):
            res.append({**a, "distance_km": round(dist, 1)})
    res.sort(key=lambda x: float(x.get("distance_km", 0.0)))
    return {"data": {"airports": res}}


def _tool_get_weather(*, city: str) -> dict:
    key = _normalize_city(city)
    if not key:
        return {"error": {"code": "invalid_args", "message": "city is required"}}
    # Deterministic mock.
    temp = (sum(ord(c) for c in key) % 25) - 5
    return {"data": {"weather": {"city": city, "temperature_c": temp, "condition": "CLEAR"}}}


def _lookup_flight(*, flight_number: str | None = None, last_name: str | None = None) -> dict[str, str] | None:
    if flight_number:
        query = flight_number.strip().upper()
        return next((flight for flight in FLIGHTS if flight.get("flight_number") == query), None)
    if last_name:
        query = last_name.strip().casefold()
        return next((flight for flight in FLIGHTS if flight.get("last_name", "").casefold() == query), None)
    return None


def _tool_get_flight_status(*, flight_number: str = None, last_name: str = None) -> dict:
    if flight_number:
        found = _lookup_flight(flight_number=flight_number)
        if found:
            return {"data": {"flight": found}}
        return {"error": {"code": "not_found", "message": f"Flight {flight_number} not found"}}
    if last_name:
        found = _lookup_flight(last_name=last_name)
        if found:
            return {"data": {"flight": found}}
        return {"error": {"code": "not_found", "message": f"Passenger {last_name} not found"}}
    return {"error": {"code": "invalid_args", "message": "flight_number or last_name is required"}}


def _current_position() -> dict[str, float | str]:
    return {"lat": 55.7558, "lon": 37.6173, "city": "Moscow"}


def _http_flight_payload(flight: dict[str, str]) -> dict[str, str]:
    return {
        "flight_number": flight["flight_number"],
        "surname": flight["last_name"],
        "status": flight["status"],
        "from": flight["from"],
        "to": flight["to"],
        "departure_time": flight["departure_time"],
        "arrival_time": flight["arrival_time"],
        "gate": flight["gate"],
        "terminal": flight["terminal"],
    }


def _tool_get_current_position() -> dict:
    return {"data": _current_position()}


def _build_route_data(
    *,
    start_lat: float,
    start_lon: float,
    end_lat: float,
    end_lon: float,
    points: int = 64,
) -> dict[str, object]:
    geometry = great_circle_geometry(
        start_lat=start_lat,
        start_lon=start_lon,
        end_lat=end_lat,
        end_lon=end_lon,
        points=points,
    )
    return {
        "geometry": geometry,
        "distance_km": round(haversine(start_lat, start_lon, end_lat, end_lon), 2),
    }


def _tool_build_route(*, from_lat: float, from_lon: float, to_lat: float, to_lon: float) -> dict:
    return {
        "data": _build_route_data(
            start_lat=from_lat,
            start_lon=from_lon,
            end_lat=to_lat,
            end_lon=to_lon,
        )
    }


def get_tools_schema() -> dict:
    return {
        "tools": [
            {
                "name": "search_airports_nearby",
                "description": "Search for airports near a city within a specified radius",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "city": {"type": "string", "description": "City name or IATA code"},
                        "radius_km": {"type": "number", "description": "Search radius in kilometers", "default": 50}
                    },
                    "required": ["city"]
                }
            },
            {
                "name": "get_weather",
                "description": "Get current weather for a city",
                "parameters": {
                    "type": "object",
                    "properties": {"city": {"type": "string", "description": "City name"}},
                    "required": ["city"]
                }
            },
            {
                "name": "get_flight_status",
                "description": "Get flight status by flight number or passenger last name",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "flight_number": {"type": "string", "description": "Flight number like SU123"},
                        "last_name": {"type": "string", "description": "Passenger last name"}
                    },
                    "required": []
                }
            },
            {
                "name": "get_current_position",
                "description": "Get current user position (GPS)",
                "parameters": {"type": "object", "properties": {}, "required": []}
            },
            {
                "name": "build_route",
                "description": "Build a route between two points",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "from_lat": {"type": "number", "description": "Starting point latitude"},
                        "from_lon": {"type": "number", "description": "Starting point longitude"},
                        "to_lat": {"type": "number", "description": "Destination latitude"},
                        "to_lon": {"type": "number", "description": "Destination longitude"}
                    },
                    "required": ["from_lat", "from_lon", "to_lat", "to_lon"]
                }
            }
        ]
    }


async def _handle_discover(msg: Msg) -> None:
    await msg.respond(json.dumps(get_tools_schema()).encode("utf-8"))


async def _handle_tool_request(msg: Msg) -> None:
    try:
        req = ToolCallRequest.model_validate(json.loads(msg.data.decode("utf-8")))
        tool = req.tool_name.strip()
        args = req.args or {}

        if tool == "search_airports_nearby":
            city = str(args.get("city") or "")
            radius_km = args.get("radius_km", 50)
            out = _tool_search_airports_nearby(city=city, radius_km=float(radius_km))
        elif tool == "get_weather":
            city = str(args.get("city") or "")
            out = _tool_get_weather(city=city)
        elif tool == "get_flight_status":
            out = _tool_get_flight_status(
                flight_number=args.get("flight_number"),
                last_name=args.get("last_name")
            )
        elif tool == "get_current_position":
            out = _tool_get_current_position()
        elif tool == "build_route":
            out = _tool_build_route(
                from_lat=float(args["from_lat"]),
                from_lon=float(args["from_lon"]),
                to_lat=float(args["to_lat"]),
                to_lon=float(args["to_lon"])
            )
        else:
            out = {"error": {"code": "unknown_tool", "message": f"Unknown tool: {tool}"}}

        if "error" in out:
            err = out["error"]
            resp = ToolCallResponse(
                trace_id=req.trace_id,
                correlation_id=req.correlation_id,
                request_id=req.request_id,
                session_id=req.session_id,
                ts_ms=now_ts_ms(),
                ok=False,
                artifact_key=f"{tool}:{req.request_id}",
                data=None,
                error=ErrorInfo(code=str(err.get("code")), message=str(err.get("message"))),
            )
        else:
            resp = ToolCallResponse(
                trace_id=req.trace_id,
                correlation_id=req.correlation_id,
                request_id=req.request_id,
                session_id=req.session_id,
                ts_ms=now_ts_ms(),
                ok=True,
                artifact_key=f"{tool}:{req.request_id}",
                data=out,
                error=None,
            )

        await msg.respond(resp.model_dump_json().encode("utf-8"))

    except Exception as exc:
        resp = ToolCallResponse(
            trace_id=uuid4(),
            correlation_id=None,
            request_id=uuid4(),
            session_id=None,
            ts_ms=now_ts_ms(),
            ok=False,
            artifact_key=None,
            data=None,
            error=ErrorInfo(code="tool_exception", message=str(exc)),
        )
        try:
            await msg.respond(resp.model_dump_json().encode("utf-8"))
        except Exception:
            pass


@app.on_event("startup")
async def _startup_nats_tools() -> None:
    app.state.nats = NATS()
    await app.state.nats.connect(
        servers=[NATS_URL],
        name="src_api_gateway",
        max_reconnect_attempts=-1,
        reconnect_time_wait=2,
        ping_interval=10,
    )
    # Subscribe to tool discovery
    await app.state.nats.subscribe(
        "nats.tools.discover",
        queue="src_api_gateway.discover.q",
        cb=_handle_discover,
    )
    # Queue group prevents duplicate tool executions if multiple api_gateway instances are running.
    await app.state.nats.subscribe(
        f"{NATS_TOOLS_PREFIX}*",
        queue="src_api_gateway.tools.q",
        cb=_handle_tool_request,
    )


@app.on_event("shutdown")
async def _shutdown_nats_tools() -> None:
    nc = getattr(app.state, "nats", None)
    if nc:
        await nc.drain()
        await nc.close()

# -------------------------
# endpoints
# -------------------------

@app.get("/api/pilot/location")
def get_current_position():
    position = _current_position()
    return {"lat": position["lat"], "lon": position["lon"]}


@app.get("/api/airports/search_by_name")
def search_by_name(query: str):
    return {
        "results": [
            a for a in AIRPORTS
            if _airport_matches_query(a, query)
        ]
    }

@app.get("/api/airports/list")
def list_airports(status: Optional[str] = None):
    if status is not None and status not in ("open", "closed"):
        return JSONResponse({"error": "status must be 'open' or 'closed'"}, status_code=400)
    return {
        "results": [
            a for a in AIRPORTS
            if status is None or a.get("status") == status
        ]
    }


@app.get("/api/airports/nearest")
def nearest_airports(
    lat: float,
    lon: float,
    radius_km: float = 300,
    status: Optional[str] = None
):
    res = []
    for a in AIRPORTS:
        if status and a["status"] != status:
            continue
        dist = haversine(lat, lon, a["lat"], a["lon"])
        if dist <= radius_km:
            res.append({**a, "distance_km": round(dist, 1)})
    return {"results": res}


@app.get("/api/airports/filter")
def filter_airports(
    min_runway_length_m: Optional[int] = None,
    runway_status: Optional[str] = None,
    surface: Optional[str] = None
):
    result = []

    for a in AIRPORTS:
        runways = a["runways"]
        filtered = []

        for r in runways:
            if min_runway_length_m and r["length_m"] < min_runway_length_m:
                continue
            if runway_status and r["status"] != runway_status:
                continue
            if surface and r["surface"] != surface:
                continue
            filtered.append(r)

        if filtered:
            result.append({**a, "runways": filtered})

    return {"results": result}


@app.get("/api/flights/status")
def flight_status(
    flight_number: str | None = Query(default=None),
    surname: str | None = Query(default=None),
):
    if isinstance(flight_number, str) and flight_number.strip():
        query = flight_number.strip().upper()
        found = _lookup_flight(flight_number=flight_number)
        if not found:
            return JSONResponse({"error": "not_found", "flight_number": query}, status_code=404)
        return _http_flight_payload(found)

    if isinstance(surname, str) and surname.strip():
        found = _lookup_flight(last_name=surname)
        if not found:
            return JSONResponse({"error": "not_found", "surname": surname.strip()}, status_code=404)
        return _http_flight_payload(found)

    return JSONResponse({"error": "flight_number or surname is required"}, status_code=400)


@app.post("/api/routes/build")
def build_route(
    start_lat: float,
    start_lon: float,
    end_lat: float,
    end_lon: float
):
    return _build_route_data(
        start_lat=start_lat,
        start_lon=start_lon,
        end_lat=end_lat,
        end_lon=end_lon,
    )

config = uvicorn.Config(
    "main:app",
    host=API_HOST,
    port=API_PORT,
    reload=False,
)

server = uvicorn.Server(config)

if __name__ == "__main__":
    asyncio.run(server.serve())
