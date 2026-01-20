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


# -------------------------
# endpoints
# -------------------------

@app.get("/api/pilot/location")
def get_current_position():
    # Москва
    return {"lat": 55.7558, "lon": 37.6173}


@app.get("/api/airports/search_by_name")
def search_by_name(query: str):
    q = query.lower()
    return {
        "results": [
            a for a in AIRPORTS
            if q in a["name"].lower() or q in a["code"].lower()
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
def flight_status(flight_number: str | None = Query(default=None)):
    if not flight_number:
        return JSONResponse({"error": "flight_number is required"}, status_code=400)

    flight_number = flight_number.strip().upper()
    statuses = ["DELAYED", "ON_TIME", "CANCELLED"]
    status = statuses[sum(ord(ch) for ch in flight_number) % len(statuses)]

    return {
        "flight_number": flight_number,
        "status": status,
        "from": "SVO",
        "to": "AMS",
        "departure_time": "2026-01-14T12:30:00Z",
        "arrival_time": "2026-01-14T15:10:00Z",
        "gate": "A12",
        "terminal": "C",
    }


@app.post("/api/routes/build")
def build_route(
    start_lat: float,
    start_lon: float,
    end_lat: float,
    end_lon: float
):
    return {
        "geometry": [
            [start_lon, start_lat],
            [end_lon, end_lat]
        ],
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
