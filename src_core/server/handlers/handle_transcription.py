import logging

from src_core.server.settings import STACK_SERVICE_NAME
from src_core.server.utils.agent import MCPAgent
from src_core.server.utils.sse import sse_log, SSEContext, register_sse_context

logger = logging.getLogger("handle_transcription")


async def handle_transcription(app, payload: dict):
    """
    Унифицированный обработчик транскрипций / текстовых сообщений.

    Делает:
      1. Логирует входящее сообщение в SSE
      2. Вызывает агент (agent_logic)
      3. Шлёт результат агента в SSE

    """

    text = (payload.get("text") or "").strip()
    if not text:
        logger.warning("Empty transcription payload")
        return

    # Логируем вход от пользователя
    await sse_log(
        {
            "type": "user_message",
            "service": "ai_agent",
            "message": text
        },
        level="info",
        app=app
    )

    logger.info("handle_transcription: '%s'", text)

    # Вызываем Агент
    agent = MCPAgent(app)
    result = await agent.run(text)

    # Агент гарантированно вернёт:
    # {
    #   "type": "agent_response",
    #   "message": "...",
    #   "client_commands": [...]
    # }
    await sse_log(result, level="info", app=app)
