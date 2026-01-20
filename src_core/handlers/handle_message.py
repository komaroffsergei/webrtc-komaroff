import logging
from aiohttp import web

from src_core.handlers.handle_transcription import handle_transcription
from src_core.settings import STACK_SERVICE_NAME
from src_core.utils.event_bus import event_log

logger = logging.getLogger("handle_message")


async def message_handler(request: web.Request):
    try:
        data = await request.json()
    except Exception as e:
        logger.error(f"Invalid JSON: {e}")
        return web.json_response({"error": "Invalid JSON"}, status=400)

    text = data.get("text", "").strip()
    if not text:
        return web.json_response({"error": "text field is required"}, status=400)

    session_id = data.get("session_id")
    edit = data.get("edit")

    await event_log(
                    "log",
                    "info",
                    {"text": text},
                    app=request.app,
                    service=STACK_SERVICE_NAME)

    payload = {"text": text}
    if session_id:
        payload["session_id"] = session_id
    if edit:
        payload["edit"] = edit

    response = await handle_transcription(request.app, payload)

    session_id_out = response.get("session_id") if isinstance(response, dict) else None
    return web.json_response(
        {"status": "ok", "session_id": session_id_out},
    )
