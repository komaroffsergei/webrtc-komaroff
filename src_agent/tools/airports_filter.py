def run(params):
    airports = params.get("airports") or []
    min_len = params.get("min_runway_length_m", 0)
    need_free = bool(params.get("require_free_runway", False))
    limit = params.get("limit")

    res = []

    for a in airports:
        if need_free:
            if not a.get("has_free_runway", False):
                continue

        if min_len > 0:
            if a.get("max_runway_length_m", 0) < min_len:
                continue

        res.append(a)

    if limit is not None:
        res = res[:limit]

    return {"results": res}
