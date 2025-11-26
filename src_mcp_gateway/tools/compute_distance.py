import math

def run(params):
    lat1 = params["lat1"]
    lon1 = params["lon1"]
    lat2 = params["lat2"]
    lon2 = params["lon2"]

    # Радиус Земли в км
    R = 6371.0

    # Перевод в радианы
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)

    # Формула гаверсинуса
    a = math.sin(dphi / 2)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    distance = R * c

    return {
        "distance_km": distance
    }
