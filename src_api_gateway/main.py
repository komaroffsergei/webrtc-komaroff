import random
import json
import os

import uvicorn
from fastapi import FastAPI
from dotenv import load_dotenv
from typing import List

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


@app.get("/api/airports/search")
def search_airports(radius_km: float, lat: float, lon: float):
    """
    Возвращает случайный поднабор аэропортов.
    Логика фильтрации НЕ РЕАЛЬНАЯ. Рыбная.
    """

    sample = random.sample(AIRPORTS, k=min(len(AIRPORTS), random.randint(1, len(AIRPORTS))))
    return sample


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


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=API_HOST,
        port=API_PORT,
        reload=False
    )
