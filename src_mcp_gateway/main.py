"""
MCP Gateway Server for aviation data tools.
This server exposes aviation-related tools through the Model Context Protocol.
"""

import os
from typing import Any, Dict

from dotenv import load_dotenv
from fastmcp import FastMCP, Context
# from fastmcp.sess import FastMCP, Context
# from mcp.server.fastmcp import FastMCP, Context
from mcp.server.session import ServerSession

# -----------------------------
# ENV
# -----------------------------
load_dotenv()

MCP_HOST = os.getenv("MCP_HOST", "127.0.0.1")
MCP_PORT = int(os.getenv("MCP_PORT", "6006"))
import logging
logger = logging.getLogger("mcp_gateway")
# -----------------------------
# MCP SERVER
# -----------------------------
mcp = FastMCP(
    name="Aviation MCP Gateway",
)

# mcp.mount

# -----------------------------
# IMPORT TOOLS IMPLEMENTATIONS
# -----------------------------

from src_mcp_gateway.tools.search_airports import run as search_airports_run
from src_mcp_gateway.tools.get_airport_by_name import run as get_airport_by_name_run
from src_mcp_gateway.tools.runway_info import run as runway_info_run
from src_mcp_gateway.tools.compute_distance import run as compute_distance_run
from src_mcp_gateway.tools.get_current_position import run as get_current_position_run
from src_mcp_gateway.tools.airports_filter import run as airports_filter_run
from src_mcp_gateway.tools.multi_route import run as multi_route_run
from src_mcp_gateway.tools.get_weather_cyclones import run as get_weather_cyclones_run
from src_mcp_gateway.tools.error_report import run as error_report_run


# -----------------------------
# MCP TOOLS
# -----------------------------

@mcp.tool()
def search_airports(
        radius_km: float,
        lat: float,
        lon: float,
        ctx: Context,
) -> Dict[str, Any]:
    """Поиск аэропортов вокруг точки."""
    try:
        return search_airports_run({
            "radius_km": radius_km,
            "lat": lat,
            "lon": lon
        })
    except Exception as e:
        logger.error(f"search_airports failed: {e}")
        raise


@mcp.tool()
def get_airport_by_name(
        query: str,
        ctx: Context,
) -> Dict[str, Any]:
    """Поиск аэропортов по наFastMCPзванию."""
    try:
        return get_airport_by_name_run({"query": query})
    except Exception as e:
        logger.error(f"get_airport_by_name failed: {e}")
        raise


@mcp.tool()
def runway_info(
        airport_id: str,
        ctx: Context,
) -> Dict[str, Any]:
    """Получить статусы и длины ВПП аэропорта."""
    try:
        return runway_info_run({"airport_id": airport_id})
    except Exception as e:
        logger.error(f"runway_info failed: {e}")
        raise


@mcp.tool()
def compute_distance(
        lat1: float,
        lon1: float,
        lat2: float,
        lon2: float,
        ctx: Context,
) -> Dict[str, Any]:
    """Вычислить расстояние между двумя координатами."""
    try:
        return compute_distance_run({
            "lat1": lat1,
            "lon1": lon1,
            "lat2": lat2,
            "lon2": lon2
        })
    except Exception as e:
        logger.error(f"compute_distance failed: {e}")
        raise


@mcp.tool()
def get_current_position(
        ctx: Context,
) -> Dict[str, Any]:
    """Получить текущее положение пилота."""
    try:
        return get_current_position_run({})
    except Exception as e:
        logger.error(f"get_current_position failed: {e}")
        raise


@mcp.tool()
def airports_filter(
        airports: list,
        min_runway_length_m: float,
        require_free_runway: bool,
        limit: int | None,
        ctx: Context,
) -> Dict[str, Any]:
    """Фильтрация списка аэропортов по условиям."""
    try:
        return airports_filter_run({
            "airports": airports,
            "min_runway_length_m": min_runway_length_m,
            "require_free_runway": require_free_runway,
            "limit": limit
        })
    except Exception as e:
        logger.error(f"airports_filter failed: {e}")
        raise


@mcp.tool()
def multi_route(
        origin: Dict[str, float],
        airports: list,
        avoid_polygons: list,
        ctx: Context
) -> Dict[str, Any]:
    """Построение маршрутов с обходом зон."""
    try:
        return multi_route_run({
            "origin": origin,
            "airports": airports,
            "avoid_polygons": avoid_polygons
        })
    except Exception as e:
        logger.error(f"multi_route failed: {e}")
        raise


@mcp.tool()
def get_weather_cyclones(ctx: Context) -> Dict[str, Any]:
    """Получить метеозоны (циклоны)."""
    try:
        return get_weather_cyclones_run({})
    except Exception as e:
        logger.error(f"get_weather_cyclones failed: {e}")
        raise


@mcp.tool()
def error_report(
        reason: str,
        ctx
) -> Dict[str, Any]:
    """Отправить сообщение об ошибке."""
    try:
        return error_report_run({"reason": reason})
    except Exception as e:
        logger.error(f"error_report failed: {e}")
        raise


# -----------------------------
# RUN SERVER
# -----------------------------
if __name__ == "__main__":
    mcp.run(
        host=MCP_HOST,
        port=MCP_PORT,
        transport="streamable-http")
