# src_mcp_gateway/schemas.py

# ---------------------------
# AIRPORT SEARCH
# ---------------------------

SEARCH_AIRPORTS_INPUT = {
    "type": "object",
    "properties": {
        "lat": {"type": "number"},
        "lon": {"type": "number"},
        "radius_km": {"type": "number", "minimum": 0}
    },
    "required": ["lat", "lon", "radius_km"]
}

SEARCH_AIRPORTS_OUTPUT = {
    "type": "object",
    "properties": {
        "results": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "name": {"type": "string"},
                    "lat": {"type": "number"},
                    "lon": {"type": "number"},
                    "distance_km": {"type": "number"}
                },
                "required": ["id", "name", "lat", "lon", "distance_km"]
            }
        }
    },
    "required": ["results"]
}

# ---------------------------
# AIRPORT BY NAME
# ---------------------------

GET_AIRPORT_BY_NAME_INPUT = {
    "type": "object",
    "properties": {
        "query": {"type": "string", "minLength": 1}
    },
    "required": ["query"]
}

GET_AIRPORT_BY_NAME_OUTPUT = {
    "type": "object",
    "properties": {
        "results": {"type": "array"}
    },
    "required": ["results"]
}

# ---------------------------
# RUNWAY INFO
# ---------------------------

GET_RUNWAY_INFO_INPUT = {
    "type": "object",
    "properties": {
        "airport_id": {"type": "string"}
    },
    "required": ["airport_id"]
}

GET_RUNWAY_INFO_OUTPUT = {
    "type": "object",
    "properties": {
        "runways": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "runway_id": {"type": "string"},
                    "status": {"type": "string"},
                    "length_m": {"type": "number"}
                },
                "required": ["runway_id", "status", "length_m"]
            }
        }
    },
    "required": ["runways"]
}

# ---------------------------
# CURRENT POSITION
# ---------------------------

GET_CURRENT_POSITION_INPUT = {"type": "object", "properties": {}}

GET_CURRENT_POSITION_OUTPUT = {
    "type": "object",
    "properties": {
        "lat": {"type": "number"},
        "lon": {"type": "number"}
    },
    "required": ["lat", "lon"]
}

# ---------------------------
# DISTANCE
# ---------------------------

COMPUTE_DISTANCE_INPUT = {
    "type": "object",
    "properties": {
        "lat1": {"type": "number"},
        "lon1": {"type": "number"},
        "lat2": {"type": "number"},
        "lon2": {"type": "number"}
    },
    "required": ["lat1", "lon1", "lat2", "lon2"]
}

COMPUTE_DISTANCE_OUTPUT = {
    "type": "object",
    "properties": {
        "distance_km": {"type": "number"}
    },
    "required": ["distance_km"]
}

# ---------------------------
# AIRPORTS FILTER
# ---------------------------

AIRPORTS_FILTER_INPUT = {
    "type": "object",
    "properties": {
        "airports": {"type": "array"},
        "min_runway_length_m": {"type": "number"},
        "require_free_runway": {"type": "boolean"},
        "limit": {"type": ["integer", "null"]}
    },
    "required": ["airports"]
}

AIRPORTS_FILTER_OUTPUT = {
    "type": "object",
    "properties": {
        "results": {"type": "array"}
    },
    "required": ["results"]
}

# ---------------------------
# MULTI ROUTE
# ---------------------------

MULTI_ROUTE_INPUT = {
    "type": "object",
    "properties": {
        "origin": {
            "type": "object",
            "properties": {"lat": {"type": "number"}, "lon": {"type": "number"}},
            "required": ["lat", "lon"]
        },
        "airports": {"type": "array"},
        "avoid_polygons": {"type": "array"}
    },
    "required": ["origin", "airports"]
}

MULTI_ROUTE_OUTPUT = {
    "type": "object",
    "properties": {
        "routes": {"type": "array"}
    },
    "required": ["routes"]
}

# ---------------------------
# WEATHER: CYCLONES
# ---------------------------

GET_WEATHER_CYCLONES_INPUT = {"type": "object", "properties": {}}

GET_WEATHER_CYCLONES_OUTPUT = {
    "type": "object",
    "properties": {
        "cyclones": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "name": {"type": "string"},
                    "polygon": {
                        "type": "array",
                        "items": {
                            "type": "array",
                            "items": {"type": "number"},
                            "minItems": 2,
                            "maxItems": 2
                        }
                    }
                },
                "required": ["id", "polygon"]
            }
        }
    },
    "required": ["cyclones"]
}
