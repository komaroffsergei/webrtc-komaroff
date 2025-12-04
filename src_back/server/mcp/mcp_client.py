import os
import logging
from fastmcp import Client

logger = logging.getLogger("mcp_client")

# адрес MCP Gateway
MCP_HOST = os.getenv("MCP_HOST", "127.0.0.1")
MCP_PORT = int(os.getenv("MCP_PORT", 6006))

# FastMCP всегда требует /mcp в конце
MCP_URL = os.getenv("MCP_URL", f"http://{MCP_HOST}:{MCP_PORT}/mcp")

# Singleton MCP client instance
_client: Client | None = None
_client_connected = False


async def get_client() -> Client:
    """
    Ленивая инициализация клиента.
    Подключение происходит один раз.
    """
    global _client, _client_connected

    if _client is None:
        _client = Client(MCP_URL)

    if not _client_connected:
        await _client.__aenter__()  # асинхронно открыть соединение
        _client_connected = True
        logger.info(f"Connected to MCP Gateway at {MCP_URL}")

    return _client


async def call_mcp(tool: str, params: dict):
    """
    Унифицированный вызов MCP-инструмента через FastMCP Client.

    Пример:
        await call_mcp("get_current_position", {})
    """
    try:
        client = await get_client()

        # ВАЖНО: FastMCPClient принимает kwargs, а не dict
        result = await client.call_tool(tool, arguments=params)

        return {
            "ok": True,
            "data": result
        }

    except Exception as e:
        logger.error("MCP tool '%s' failed: %s", tool, e)
        return {
            "ok": False,
            "error": str(e)
        }
