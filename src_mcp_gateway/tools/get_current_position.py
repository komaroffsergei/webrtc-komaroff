import random

def run(params):
    base_lat = 55.75
    base_lon = 37.61
    delta = 0.3

    lat = base_lat + random.uniform(-delta, delta)
    lon = base_lon + random.uniform(-delta, delta)

    return {
        "lat": round(lat, 6),
        "lon": round(lon, 6)
    }
