from ..utils.sse import sse_log, logger
import aiohttp
import json


# ------------------------------
# Helper: вызвать LLM
# ------------------------------
async def call_llm(prompt: str):
    async with aiohttp.ClientSession() as session:
        async with session.post(
            "http://127.0.0.1:6007/generate",
            json={"prompt": prompt, "max_tokens": 200}
        ) as resp:
            resp.raise_for_status()
            data = await resp.json()
            return data["text"]


# ------------------------------
# Helper: вызвать MCP
# ------------------------------
async def call_mcp(tool: str, params: dict):
    async with aiohttp.ClientSession() as session:
        async with session.post(
            "http://127.0.0.1:6006/invoke",
            json={"tool": tool, "params": params}
        ) as resp:
            resp.raise_for_status()
            data = await resp.json()
            return data["result"]


# ------------------------------
# Helper: понять, это tool-call?
# ------------------------------
def is_tool_call(text: str):
    try:
        obj = json.loads(text)
        return isinstance(obj, dict) and "tool" in obj and "params" in obj
    except:
        return False


# ------------------------------
# Основная логика MCP-агента
# ------------------------------
async def agent_logic(user_text: str):
    """
    Ведёт цепочку LLM → MCP → LLM → ... пока не получит финальный ответ.
    """

    # 1. Первый вызов модели
    msg = await call_llm(user_text)

    # 2. Пока модель вызывает инструменты
    while True:
        if is_tool_call(msg):
            call = json.loads(msg)
            tool = call["tool"]
            params = call["params"]

            # вызов инструмента
            result = await call_mcp(tool, params)

            # снова в модель с результатом
            msg = await call_llm(
                f"Результат инструмента {tool}: {json.dumps(result, ensure_ascii=False)}. Продолжай."
            )
        else:
            return msg


# ------------------------------
# ПЕРЕПИСАННЫЙ handle_transcription
# ------------------------------
async def handle_transcription(app, data):
    try:
        text = data.get("text", "").strip()
        if not text:
            return

        # Лог голого текста от Whisper
        await sse_log(app, f"Whisper: {text}", level="info")

        # -------------------
        # Вызов MCP-агента
        # -------------------
        text = "Найди аэропорт в радиусе 100 км."
        answer = await agent_logic(text)

        # Отображаем ответ агента в UI (SSE)
        await sse_log(app, f"Agent: {answer}", level="info")

    except Exception as e:
        logger.warning(f"agent error: {e}")
