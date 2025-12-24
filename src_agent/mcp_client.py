# src_agent/mcp_client.py
import logging
from src_agent.tools.old.search_airports import run as search_airports_run
from src_agent.tools.old.get_airport_by_name import run as get_airport_by_name_run
from src_agent.tools.old.runway_info import run as runway_info_run
from src_agent.tools.old.compute_distance import run as compute_distance_run
from src_agent.tools.old.get_current_position import run as get_current_position_run
from src_agent.tools.old.airports_filter import run as airports_filter_run
from src_agent.tools.old.multi_route import run as multi_route_run
from src_agent.tools.old.get_weather_cyclones import run as get_weather_cyclones_run

logger = logging.getLogger("agent.mcp_client")

TOOL_MAP = {
    "search_airports": search_airports_run,
    "get_airport_by_name": get_airport_by_name_run,
    "runway_info": runway_info_run,
    "compute_distance": compute_distance_run,
    "get_current_position": get_current_position_run,
    "airports_filter": airports_filter_run,
    "multi_route": multi_route_run,
    "get_weather_cyclones": get_weather_cyclones_run,
}

class MCPClient:
    async def call_tool(self, tool: str, params: dict):
        func = TOOL_MAP.get(tool)
        if func is None:
            error = f"Unknown tool: {tool}"
            logger.error(error)
            return {"ok": False, "error": error}
        try:
            result = func(params)
            return {"ok": True, "data": result}
        except Exception as e:
            logger.error("Tool '%s' failed: %s", tool, e)
            return {"ok": False, "error": str(e)}