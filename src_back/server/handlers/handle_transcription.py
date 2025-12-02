import logging
import aiohttp
import json
import os
import asyncio

from mcp.client.session_group import ClientSessionGroup, StreamableHttpParameters
from mcp import types as mcp_types
from shared.sse import sse_log
from server.utils.sse import get_sse_context

logger = logging.getLogger("handle_transcription")

LLM_URL = os.getenv("LLM_URL", "http://127.0.0.1:6007/generate")
LLM_MAX_TOKENS = int(os.getenv("LLM_STEP_TOKENS", "512"))
OBSERVATION_MAX_CHARS = int(os.getenv("MCP_OBSERVATION_LIMIT", "1500"))


# ------------------------------
# Helper: вызвать MCP
# ------------------------------
MCP_HOST = os.getenv("MCP_HOST", "127.0.0.1")
MCP_PORT = int(os.getenv("MCP_PORT", "6006"))
MCP_URL = os.getenv("MCP_STREAMABLE_URL", f"http://{MCP_HOST}:{MCP_PORT}/mcp")

_mcp_group: ClientSessionGroup | None = None
_mcp_lock = asyncio.Lock()


async def _ensure_mcp_group() -> ClientSessionGroup:
    global _mcp_group
    if _mcp_group is not None:
        return _mcp_group

    async with _mcp_lock:
        if _mcp_group is None:
            group = ClientSessionGroup()
            await group.__aenter__()
            await group.connect_to_server(StreamableHttpParameters(url=MCP_URL))
            _mcp_group = group
    return _mcp_group


def _format_tool_result(result: mcp_types.CallToolResult):
    if result.structuredContent is not None:
        return result.structuredContent

    text_blocks = [
        block.text
        for block in result.content
        if isinstance(block, mcp_types.TextContent)
    ]

    combined = "\n".join(text_blocks).strip()
    if not combined:
        return result.model_dump()

    try:
        return json.loads(combined)
    except json.JSONDecodeError:
        return combined


async def call_mcp(tool: str, params: dict):
    group = await _ensure_mcp_group()
    call_result = await group.call_tool(tool, arguments=params)
    if isinstance(call_result, mcp_types.CallToolResult):
        return _format_tool_result(call_result)
    return call_result


async def call_llm(summary: str, observations: list[str], user_request: str, max_tokens: int = LLM_MAX_TOKENS):
    payload = {
        "summary": summary,
        "observations": observations,
        "user_request": user_request,
        "max_tokens": max_tokens,
    }
    async with aiohttp.ClientSession() as session:
        async with session.post(
            LLM_URL,
            json=payload,
        ) as resp:
            resp.raise_for_status()
            data = await resp.json()
            parsed = data.get("parsed")
            if isinstance(parsed, str):
                try:
                    parsed = json.loads(parsed)
                except json.JSONDecodeError:
                    parsed = None
            data["parsed"] = parsed
            return data

def _format_observation(tool_name: str, result: object) -> str:
    serialized = json.dumps(result, ensure_ascii=False)
    if len(serialized) > OBSERVATION_MAX_CHARS:
        serialized = serialized[: OBSERVATION_MAX_CHARS - 3] + "..."
    return f"{tool_name}: {serialized}"


async def agent_logic(app, user_text: str, max_steps: int = 12) -> str:
    """
    MCP-агент с прозрачным мышлением и компактной историей.
    """
    sse_ctx = get_sse_context(app)
    history_summary = ""
    observations: list[str] = []

    for step in range(1, max_steps + 1):
        raw_response = await call_llm(history_summary, observations, user_text, max_tokens=LLM_MAX_TOKENS)

        await sse_log(sse_ctx, f"LLM raw (шаг {step}): {raw_response}", level="debug")

        data = raw_response.get("parsed")
        if not isinstance(data, dict):
            await sse_log(sse_ctx, f"Некорректный ответ модели на шаге {step}: {raw_response}", level="error")
            return "Ошибка: модель вернула невалидный JSON."

        thought = data.get("thought", "Нет мысли.")
        await sse_log(sse_ctx, f"Мысль агента (шаг {step}): {thought}", level="info")

        history_candidate = data.get("history")
        if isinstance(history_candidate, str) and history_candidate.strip():
            history_summary = history_candidate.strip()

        final_result = (data.get("final_result") or "").strip()
        tool_calls = data.get("tool_calls") or []

        if final_result:
            await sse_log(sse_ctx, f"Финальный ответ: {final_result}", level="success")
            return final_result

        if not tool_calls:
            await sse_log(sse_ctx, "Агент не вернул вызовы инструментов и не дал финальный ответ", level="warning")
            return "Ошибка: агент завершил шаги, но не дал финальный ответ."

        next_observations: list[str] = []
        for item in tool_calls:
            call = item.get("call")
            if not isinstance(call, dict):
                continue
            tool_name = call.get("tool")
            params = call.get("parameters", {})
            if not isinstance(tool_name, str):
                continue
            if not isinstance(params, dict):
                params = {}

            await sse_log(sse_ctx, f"Вызов инструмента: {tool_name} (обоснование: {item.get('thought', 'нет')})", level="info")

            try:
                result = await call_mcp(tool_name, params)
                await sse_log(sse_ctx, f"Результат {tool_name}: {result}", level="debug")
            except Exception as e:
                result = {"error": str(e)}
                await sse_log(sse_ctx, f"Ошибка инструмента {tool_name}: {e}", level="error")

            item["result"] = result
            next_observations.append(_format_observation(tool_name, result))

        observations = next_observations

    await sse_log(sse_ctx, "Превышено максимальное количество шагов", level="error")
    return "Ошибка: агент не смог завершить задачу за отведённое количество шагов."
# ------------------------------
# handle_transcription — теперь просто вызывает новый agent_logic
# ------------------------------
async def handle_transcription(app, data):
    try:
        text = (data.get("text", "") if isinstance(data, dict) else "").strip()
        if not text:
            return

        sse_ctx = get_sse_context(app)
        await sse_log(sse_ctx, f"Whisper: {text}", level="info")

        final_answer = await agent_logic(app, text)

        await sse_log(sse_ctx, f"MCP answer: {final_answer}", level="success")
        await sse_log(sse_ctx, f"MCP answer: {final_answer}", name="message", level="success")

    except Exception as e:
        logger.error(f"agent crash: {e}")
        await sse_log(sse_ctx, f"Ошибка агента: {e}", level="error")
