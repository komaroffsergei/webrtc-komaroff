import math


def run(params):
    """
    Расчёт расстояния между двумя точками по сфере (км).

    Вход:
      {
        "lat1": float,
        "lon1": float,
        "lat2": float,
        "lon2": float
      }

    Выход:
      { "distance_km": float }
    """
    lat1 = float(params["lat1"])
    lon1 = float(params["lon1"])
    lat2 = float(params["lat2"])
    lon2 = float(params["lon2"])

    R = 6371.0

    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)

    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(
        dlambda / 2
    ) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    distance = R * c

    return {"distance_km": float(distance)}
