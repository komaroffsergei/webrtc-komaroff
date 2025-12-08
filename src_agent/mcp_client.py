import os
import logging
from fastmcp import Client
import asyncio

logger = logging.getLogger("agent.mcp_client")


class MCPClient:
    def __init__(self):
        self._client = None
        self._connected = False

    async def get_client(self) -> Client:
        from settings import MCP_URL

        if self._client is None:
            self._client = Client(MCP_URL)

        if not self._connected:
            await self._client.__aenter__()
            self._connected = True
            logger.info(f"Connected to MCP Gateway at {MCP_URL}")

        return self._client

    async def call_tool(self, tool: str, params: dict):
        try:
            client = await self.get_client()
            # FastMCPClient принимает аргументы в виде ключевых параметров
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