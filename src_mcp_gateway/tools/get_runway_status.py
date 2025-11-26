import requests

from config_loader import load_settings

SETTINGS = load_settings()
API_URL = SETTINGS["services"]["runways_api"]
TIMEOUT = SETTINGS["network"]["timeout_seconds"]

def run(params):
    airport_id = params["airport_id"]

    url = f"{API_URL}/{airport_id}/runways"

    response = requests.get(url, timeout=TIMEOUT)
    response.raise_for_status()

    return response.json()
