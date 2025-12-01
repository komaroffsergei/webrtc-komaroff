"""
MCP Gateway Server for aviation data tools.
This server exposes aviation-related tools through the Model Context Protocol.
"""
import os
from typing import Any, Dict
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP, Context
from mcp.server.session import ServerSession

# Загружаем переменные окружения
load_dotenv()

MCP_HOST = os.getenv("MCP_HOST", "127.0.0.1")
MCP_PORT = int(os.getenv("MCP_PORT", "6006"))

# Создаем MCP сервер
mcp = FastMCP(
    name="Aviation MCP Gateway",
    # description="Инструменты доступа к авиационным данным: поиск аэродромов, статусы полос, георасчёты.",
    stateless_http=True,
    json_response=True,
    host=MCP_HOST,
    port=MCP_PORT,
)

# Импортируем инструменты
from tools.search_airports import run as search_airports_run
from tools.get_runway_status import run as get_runway_status_run
from tools.compute_distance import run as compute_distance_run
from tools.get_airport_by_name import run as get_airport_by_name_run
from tools.get_current_position import run as get_current_position_run
from tools.error_report import run as error_report_run


# Определяем инструменты с помощью декораторов MCP
@mcp.tool()
def search_airports(
        radius_km: float,
        lat: float,
        lon: float,
        ctx: Context[ServerSession, None]
) -> Dict[str, Any]:
    """
    Возвращает список аэродромов в пределах указанного радиуса от заданной точки.

    Параметры:
    radius_km: Радиус поиска в километрах
    lat: Широта центральной точки
    lon: Долгота центральной точки
    """
    try:
        result = search_airports_run({
            "radius_km": radius_km,
            "lat": lat,
            "lon": lon
        })
        return result
    except Exception as e:
        ctx.error_sync(f"Error in search_airports: {str(e)}")
        raise


@mcp.tool()
def get_runway_status(
        airport_id: str,
        ctx: Context[ServerSession, None]
) -> Dict[str, Any]:
    """
    Возвращает список полос аэродрома и их статусы.

    Параметры:
    airport_id: Идентификатор аэропорта
    """
    try:
        result = get_runway_status_run({
            "airport_id": airport_id
        })
        return result
    except Exception as e:
        ctx.error_sync(f"Error in get_runway_status: {str(e)}")
        raise


@mcp.tool()
def compute_distance(
        lat1: float,
        lon1: float,
        lat2: float,
        lon2: float,
        ctx: Context[ServerSession, None]
) -> Dict[str, Any]:
    """
    Вычисляет расстояние между двумя точками в километрах.

    Параметры:
    lat1: Широта первой точки
    lon1: Долгота первой точки
    lat2: Широта второй точки
    lon2: Долгота второй точки
    """
    try:
        result = compute_distance_run({
            "lat1": lat1,
            "lon1": lon1,
            "lat2": lat2,
            "lon2": lon2
        })
        return result
    except Exception as e:
        ctx.error_sync(f"Error in compute_distance: {str(e)}")
        raise


@mcp.tool()
def get_airport_by_name(
        query: str,
        ctx: Context[ServerSession, None]
) -> Dict[str, Any]:
    """
    Получить координаты аэропорта по названию или его части.

    Параметры:
    query: Название или часть названия аэропорта
    """
    try:
        result = get_airport_by_name_run({
            "query": query
        })
        return result
    except Exception as e:
        ctx.error_sync(f"Error in get_airport_by_name: {str(e)}")
        raise


@mcp.tool()
def get_current_position(
        ctx: Context[ServerSession, None]
) -> Dict[str, Any]:
    """
    Возвращает текущие координаты исходной точки (например, положение пилота).
    """
    try:
        result = get_current_position_run({})
        return result
    except Exception as e:
        ctx.error_sync(f"Error in get_current_position: {str(e)}")
        raise


@mcp.tool()
def error_report(
        reason: str,
        ctx: Context[ServerSession, None]
) -> Dict[str, Any]:
    """
    Сообщить о нарушении правил или невозможности корректно сформировать ответ.

    Параметры:
    reason: Причина ошибки или нарушения
    """
    try:
        result = error_report_run({
            "reason": reason
        })
        return result
    except Exception as e:
        ctx.error_sync(f"Error in error_report: {str(e)}")
        raise


# Запуск сервера
if __name__ == "__main__":
    # Рекомендуемый транспорт для production
    mcp.run(transport="streamable-http")
