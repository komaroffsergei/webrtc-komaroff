import asyncio
import math
from typing import List, Optional

import uvicorn
from fastapi import FastAPI, Query
from fastapi.responses import JSONResponse
import json
import os

app = FastAPI(title="Mock Aviation API")

BASE_DIR = os.path.dirname(__file__)
DATA_FILE = os.path.join(BASE_DIR, "data", "airports.json")

API_PORT = int(os.getenv("API_PORT", "8100"))
API_HOST = os.getenv("API_HOST", "0.0.0.0")

with open(DATA_FILE, "r", encoding="utf-8") as f:
    AIRPORTS = json.load(f)


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

# -------------------------
# endpoints
# -------------------------

@app.get("/api/pilot/location")
def get_current_position():
    # Москва
    return {"lat": 55.7558, "lon": 37.6173}


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
    flights = [
        {
            "flight_number": "SU123",
            "surname": "Иванов",
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
            "surname": "Петров",
            "status": "DELAYED",
            "from": "DME",
            "to": "LED",
            "departure_time": "2026-01-14T09:10:00Z",
            "arrival_time": "2026-01-14T10:35:00Z",
            "gate": "B07",
            "terminal": "B",
        },
    ]

    if isinstance(flight_number, str) and flight_number.strip():
        q = flight_number.strip().upper()
        found = next((f for f in flights if f.get("flight_number") == q), None)
        if not found:
            return JSONResponse({"error": "not_found", "flight_number": q}, status_code=404)
        return found

    if isinstance(surname, str) and surname.strip():
        q = surname.strip().casefold()
        found = next((f for f in flights if isinstance(f.get("surname"), str) and f["surname"].strip().casefold() == q), None)
        if not found:
            return JSONResponse({"error": "not_found", "surname": surname.strip()}, status_code=404)
        return found

    return JSONResponse({"error": "flight_number or surname is required"}, status_code=400)


@app.post("/api/routes/build")
def build_route(
    start_lat: float,
    start_lon: float,
    end_lat: float,
    end_lon: float
):
    geometry = great_circle_geometry(
        start_lat=start_lat,
        start_lon=start_lon,
        end_lat=end_lat,
        end_lon=end_lon,
        points=64,
    )
    return {
        "geometry": geometry,
        "distance_km": round(
            haversine(start_lat, start_lon, end_lat, end_lon), 2
        )
    }

config = uvicorn.Config(
    "main:app",
    host=API_HOST,
    port=API_PORT,
    reload=False,
)

server = uvicorn.Server(config)

if __name__ == "__main__":
    asyncio.run(server.serve())
