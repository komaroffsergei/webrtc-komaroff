import requests

from src_agent.settings import PILOT_API_URL, TIMEOUT_SECONDS


def run(params):
    """
    Текущая позиция "пилота" / исходной точки.

    Вход:
      {}  (без параметров)

    Выход:
      { "lat": float, "lon": float }
    """
    r = requests.get(PILOT_API_URL, timeout=TIMEOUT_SECONDS)
    r.raise_for_status()
    data = r.json()

    return {
        "lat": float(data["lat"]),
        "lon": float(data["lon"]),
    }
