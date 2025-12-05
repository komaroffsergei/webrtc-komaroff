import logging

from src_core.server.settings import STACK_SERVICE_NAME
from src_core.server.utils.agent import MCPAgent
from src_core.server.utils.sse import sse_log, SSEContext, register_sse_context

logger = logging.getLogger("handle_transcription")


import json
import logging

from src_core.server.settings import STACK_SERVICE_NAME, AGENT_FRAMES_SUBJECT
from src_core.server.utils.sse import sse_log

logger = logging.getLogger("handle_transcription")


async def handle_transcription(app, payload: dict):
    """
    Унифицированный обработчик транскрипций / текстовых сообщений.

    1) Логирует входящее сообщение в SSE
    2) Шлёт текст в агент-сервис по NATS (request/reply)
    3) Результат агента шлёт в SSE
    """

    text = (payload.get("text") or "").strip()
    if not text:
        logger.warning("Empty transcription payload")
        return

    # 1. Логируем вход от пользователя
    await sse_log(
        {
            "type": "user_message",
            "service": "ai_agent",
            "message": text,
        },
        level="info",
        app=app,
    )

    logger.info("handle_transcription: '%s'", text)

    # 2. RPC к агенту через NATS
    nats_client = app["services"]["nats_client"]

    request_payload = {
        "service": STACK_SERVICE_NAME,
        "text": text,
    }

    try:
        msg = await nats_client.request(
            AGENT_FRAMES_SUBJECT,
            json.dumps(request_payload, ensure_ascii=False).encode("utf-8"),
            timeout=60.0,
        )
    except Exception as e:
        logger.error("NATS request to agent failed: %s", e)
        await sse_log(
            {
                "type": "agent_error",
                "service": "ai_agent",
                "error": f"NATS request failed: {e}",
            },
            level="error",
            app=app,
        )
        return

    try:
        response = json.loads(msg.data.decode("utf-8"))
    except Exception as e:
        logger.error("Invalid JSON from agent via NATS: %s, raw=%r", e, msg.data)
        await sse_log(
            {
                "type": "agent_error",
                "service": "ai_agent",
                "error": f"Invalid JSON from agent: {e}",
            },
            level="error",
            app=app,
        )
        return

    # ожидаемый формат:
    # {
    #   "input": "...",
    #   "output": {
    #       "agent": "...",
    #       "result": {
    #           "plan": ...,
    #           "tool_results": ...,
    #           "final": "..."
    #       }
    #   },
    #   "time": ...
    # }
    output = response.get("output") or {}
    result = output.get("result") or output

    if isinstance(result, dict):
        final_text = result.get("final") or ""
    else:
        final_text = str(result)

    # 3. Логируем ответ агента в SSE в том же формате, что и раньше
    await sse_log(
        {
            "type": "agent_response",
            "service": "ai_agent",
            "message": final_text,
            "raw": result,
        },
        level="info",
        app=app,
    )

