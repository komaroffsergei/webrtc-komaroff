import requests

from src_mcp_gateway.config_loader import load_settings

SETTINGS = load_settings()
API_URL = SETTINGS["services"]["pilot_api"]
TIMEOUT = SETTINGS["network"]["timeout_seconds"]


def run(params):
    """
    Текущая позиция "пилота" / исходной точки.

    Вход:
      {}  (без параметров)

    Выход:
      { "lat": float, "lon": float }
    """
    r = requests.get(API_URL, timeout=TIMEOUT)
    r.raise_for_status()
    data = r.json()

    return {
        "lat": float(data["lat"]),
        "lon": float(data["lon"]),
    }
