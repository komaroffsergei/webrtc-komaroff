from __future__ import annotations

import json
from uuid import UUID, uuid4

from aiohttp import web

from src_core.settings import NATS_REQUEST_TIMEOUT
from src_shared.contracts import HistoryGetRequest, HistoryGetResponse, now_ts_ms


async def history_handler(request: web.Request) -> web.Response:
    raw_session_id = str(request.query.get("session_id") or "").strip()
    if not raw_session_id:
        raise web.HTTPBadRequest(
            text=json.dumps({"error": "session_id is required"}),
            content_type="application/json",
        )

    try:
        session_id = UUID(raw_session_id)
    except Exception as exc:
        raise web.HTTPBadRequest(
            text=json.dumps({"error": "session_id must be a valid UUID"}),
            content_type="application/json",
        ) from exc

    raw_limit = str(request.query.get("limit") or "").strip()
    limit = 200
    if raw_limit:
        try:
            limit = max(1, min(int(raw_limit), 1000))
        except Exception as exc:
            raise web.HTTPBadRequest(
                text=json.dumps({"error": "limit must be an integer"}),
                content_type="application/json",
            ) from exc

    req = HistoryGetRequest(
        trace_id=uuid4(),
        correlation_id=None,
        request_id=uuid4(),
        session_id=session_id,
        ts_ms=now_ts_ms(),
        limit=limit,
    )

    nc = request.app["services"]["nats_client"]
    subject = request.app["vars"]["NATS_AGENT_HISTORY_SUBJECT"]
    msg = await nc.request(
        subject,
        req.model_dump_json().encode("utf-8"),
        timeout=NATS_REQUEST_TIMEOUT,
    )
    raw = json.loads(msg.data.decode("utf-8"))
    resp = HistoryGetResponse.model_validate(raw)
    status = 200 if resp.ok else 500
    return web.json_response(
        {
            "ok": resp.ok,
            "items": [item.model_dump() for item in resp.items],
            "runtime_context": resp.runtime_context,
            "error": resp.error.model_dump() if resp.error else None,
            "session_id": str(resp.session_id) if resp.session_id else None,
        },
        status=status,
    )
