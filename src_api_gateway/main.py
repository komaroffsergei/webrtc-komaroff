import asyncio
import math
import json
import os
import random
from typing import List, Dict, Any

import uvicorn
from fastapi import FastAPI, HTTPException, Query
from dotenv import load_dotenv

load_dotenv()

API_PORT = int(os.getenv("API_PORT", "8100"))
API_HOST = os.getenv("API_HOST", "0.0.0.0")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")

with open(os.path.join(DATA_DIR, "airports.json"), "r") as f:
    AIRPORTS: List[Dict[str, Any]] = json.load(f)

with open(os.path.join(DATA_DIR, "runway_status.json"), "r") as f:
    RUNWAYS: List[Dict[str, Any]] = json.load(f)

with open(os.path.join(DATA_DIR, "weather_cyclones.json"), "r") as f:
    CYCLONES = json.load(f)

app = FastAPI(title="API Gateway (mocked aviation data)")


# -------------------------------------------------------------
# Helpers
# -------------------------------------------------------------

def haversine(lat1, lon1, lat2, lon2) -> float:
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


# -------------------------------------------------------------
# Airports
# -------------------------------------------------------------

@app.get("/api/airports/search_by_name")
def search_by_name(query: str = Query(..., min_length=1)):
    q = query.lower()
    matches = [a for a in AIRPORTS if q in a["name"].lower()]
    return {"results": matches}


@app.get("/api/airports/search")
def search_airports(
    lat: float,
    lon: float,
    radius_km: float = 50.0,
):
    res = []
    for a in AIRPORTS:
        dist = haversine(lat, lon, a["lat"], a["lon"])
        if dist <= radius_km:
            res.append({
                "id": a["id"],
                "name": a["name"],
                "lat": a["lat"],
                "lon": a["lon"],
                "distance_km": round(dist, 2)
            })
    return {"results": res}


@app.get("/api/airports/{airport_id}/runways")
def get_runways(airport_id: str):
    # Mocked: random subset of runway statuses
    count = random.randint(1, len(RUNWAYS))
    sample = random.sample(RUNWAYS, count)
    return {"runways": sample}


# -------------------------------------------------------------
# Pilot / Position
# -------------------------------------------------------------

@app.get("/api/pilot/location")
def pilot_location():
    # Mocked random pilot position
    lat = random.uniform(54.5, 56.5)
    lon = random.uniform(36.5, 39.0)
    return {"lat": lat, "lon": lon}


# -------------------------------------------------------------
# Routes
# -------------------------------------------------------------

@app.get("/api/routes/nearest")
def get_nearest_route(
    lat: float,
    lon: float,
    radius_km: float | None = None,
    require_free_runway: bool = False
):
    """
    Mock route search:
    - find nearest airport
    - optionally require free runway
    - return a mocked single route structure
    """
    candidates = []

    for a in AIRPORTS:
        dist = haversine(lat, lon, a["lat"], a["lon"])
        if radius_km is not None and dist > radius_km:
            continue

        # free runway filter
        if require_free_runway:
            has_free = any(r["status"] == "free" for r in RUNWAYS)
            if not has_free:
                continue

        candidates.append((dist, a))

    if not candidates:
        return {"fallback": True, "reason": "no candidates"}

    candidates.sort(key=lambda x: x[0])
    best_dist, best_airport = candidates[0]

    route_geometry = [
        [lon, lat],
        [best_airport["lon"], best_airport["lat"]],
    ]

    return {
        "fallback": False,
        "distance_km": round(best_dist, 2),
        "airport": best_airport,
        "geometry": route_geometry,
    }

@app.get("/api/weather/cyclones")
def get_cyclones():
    """
    Моковые зоны циклонов.

    Выход:
      {
        "cyclones": [
          {
            "id": str,
            "name": str,
            "polygon": [[lon, lat], ...]
          }, ...
        ]
      }
    """
    return {"cyclones": CYCLONES}


# -------------------------------------------------------------
# Boot
# -------------------------------------------------------------
config = uvicorn.Config(
    "main:app",
    host=API_HOST,
    port=API_PORT,
    reload=False,
)

server = uvicorn.Server(config)

if __name__ == "__main__":
    asyncio.run(server.serve())
