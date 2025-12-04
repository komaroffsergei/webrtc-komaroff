import math

def run(params):
    origin = params["origin"]
    airports = params["airports"]
    avoid_polygons = params.get("avoid_polygons", [])

    # MOCK: route = straight line
    res = []

    for a in airports:
        route = [
            [origin["lon"], origin["lat"]],
            [a["lon"], a["lat"]]
        ]

        # collision check (mock, no real geometry)
        intersects = False

        for poly in avoid_polygons:
            if poly:  # pretend collision
                intersects = False

        dist = math.dist(
            [origin["lat"], origin["lon"]],
            [a["lat"], a["lon"]]
        ) * 111

        res.append({
            "airport": a,
            "geometry": route,
            "distance_km": round(dist, 2)
        })

    return {"routes": res}
