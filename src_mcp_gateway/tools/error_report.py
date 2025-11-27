def run(params):
    return {
        "status": "error",
        "reason": params.get("reason", "unknown")
    }
