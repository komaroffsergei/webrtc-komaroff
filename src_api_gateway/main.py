import asyncio
import math
import random
import json
import os

import uvicorn
from fastapi import FastAPI
from dotenv import load_dotenv

load_dotenv()

API_PORT = int(os.getenv("API_PORT", "8100"))
API_HOST = os.getenv("API_HOST", "127.0.0.1")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")

with open(os.path.join(DATA_DIR, "airports.json"), "r") as f:
    AIRPORTS = json.load(f)

with open(os.path.join(DATA_DIR, "runway_status.json"), "r") as f:
    RUNWAY_STATUSES = json.load(f)

app = FastAPI()

@app.get("/api/airports/search_by_name")
def find_by_name(query: str):
    # фильтруем моковые аэропорты: если query в имени
    matches = [a for a in AIRPORTS if query.lower() in a["name"].lower()]
    return matches

def haversine(lat1, lon1, lat2, lon2):
    R = 6371  # радиус Земли
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat/2) ** 2 +
         math.cos(math.radians(lat1)) *
         math.cos(math.radians(lat2)) *
         math.sin(dlon/2) ** 2)
    return 2 * R * math.asin(math.sqrt(a))


@app.get("/api/airports/search")
def search_airports(radius_km: float, lat: float, lon: float):
    """
    Возвращает аэропорты в пределах радиуса.
    Если нет — делает fallback: возвращает ближайший + расстояние.
    """

    in_radius = []

    for a in AIRPORTS:
        dist = haversine(lat, lon, a["lat"], a["lon"])
        if dist <= radius_km:
            item = dict(a)
            item["distance_km"] = round(dist, 2)
            in_radius.append(item)

    # Если что-то найдено — отдаём список
    if in_radius:
        return {
            "fallback": False,
            "results": in_radius
        }

    # FALLBACK — ищем ближайший аэропорт
    best = None
    best_dist = 999999

    for a in AIRPORTS:
        dist = haversine(lat, lon, a["lat"], a["lon"])
        if dist < best_dist:
            best_dist = dist
            best = a

    return {
        "fallback": True,
        "distance_km": round(best_dist, 2),
        "airport": best
    }


@app.get("/api/airports/{airport_id}/runways")
def get_runways(airport_id: str):
    """
    Возвращает случайный набор статусов полос.
    """
    count = random.randint(1, len(RUNWAY_STATUSES))
    sample = random.sample(RUNWAY_STATUSES, k=count)
    return sample


@app.get("/api/pilot/location")
def get_current_location():
    """
    Возвращает случайное текущее местоположение пилота.
    """
    lat = random.uniform(54.5, 56.5)
    lon = random.uniform(36.5, 39.0)

    return {"lat": lat, "lon": lon}


config = uvicorn.Config(
    "main:app",
    host=API_HOST,
    port=API_PORT,
    reload=False,
)

server = uvicorn.Server(config)

if __name__ == "__main__":
    asyncio.run(server.serve())
