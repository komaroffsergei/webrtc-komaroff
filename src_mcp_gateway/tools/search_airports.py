import requests

from config_loader import load_settings

SETTINGS = load_settings()
API_URL = SETTINGS["services"]["airports_api"]
TIMEOUT = SETTINGS["network"]["timeout_seconds"]

def run(params):
    radius_km = params["radius_km"]
    lat = params["lat"]
    lon = params["lon"]

    response = requests.get(
        API_URL,
        params={
            "radius_km": radius_km,
            "lat": lat,
            "lon": lon
        },
        timeout=TIMEOUT
    )

    response.raise_for_status()

    return response.json()
