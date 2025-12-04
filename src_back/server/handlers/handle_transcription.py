import logging

from shared.sse import sse_log
from src_back.server.utils.agent import MCPAgent
from shared.sse.context import GLOBAL_SSE_CONTEXT as ctx
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
        ctx,
        {
            "type": "user_message",
            "service": "ai_agent",
            "message": text
        },
        level="info"
    )

    logger.info("handle_transcription: '%s'", text)

    # Вызываем Агент
    agent = MCPAgent(ctx)
    result = await agent.run(text)

    # Агент гарантированно вернёт:
    # {
    #   "type": "agent_response",
    #   "message": "...",
    #   "client_commands": [...]
    # }
    await sse_log(ctx, result, level="info")
