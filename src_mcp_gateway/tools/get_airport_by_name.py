import requests

from config_loader import load_settings

SETTINGS = load_settings()
API_URL = SETTINGS["services"]["airports_api"]
TIMEOUT = SETTINGS["network"]["timeout_seconds"]

def run(params):
    query = params["query"]
    # В api_gateway должен быть соответствующий endpoint
    r = requests.get(API_URL + "/search_by_name", params={"query": query}, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()
