from __future__ import annotations

from typing import Any

from src_shared.contracts import WorkflowRunRequest, WorkflowRunResponse

from src_langgraph.config_loader import dict_value, load_config, text_block
from src_langgraph.responses import done_response, failed_response, next_runtime
from src_langgraph.runtime_io import RuntimeIO
from src_langgraph.scenarios.common import extract_llm_text, extract_nested_data, normalize_tool_params

_CFG = load_config("find_nearest_airport")
_PROMPTS = dict_value(_CFG.get("prompts"))
_TOOLS = dict_value(_CFG.get("tools"))
_DEFAULTS = dict_value(_CFG.get("defaults"))
_SCHEMAS = dict_value(_CFG.get("schemas"))

TOOL_GET_POSITION = str(_TOOLS.get("position") or "get_current_position")
TOOL_SEARCH_AIRPORTS = str(_TOOLS.get("search_airports") or "search_airports_nearby")
TOOL_BUILD_ROUTE = str(_TOOLS.get("build_route") or "build_route")
DEFAULT_CITY = str(_DEFAULTS.get("search_city") or "Moscow")
DEFAULT_RADIUS_KM = float(_DEFAULTS.get("search_radius_km") or 50)
SEARCH_PARAMS_TASK = text_block(
    _PROMPTS.get("search_params_task"),
    "Подготовь параметры для поиска ближайших аэропортов.\nЕсли город не указан явно, используй данные о текущей позиции из tool_results.",
)
ROUTE_PARAMS_TASK = text_block(
    _PROMPTS.get("route_params_task"),
    "Подготовь параметры для построения маршрута до выбранного аэропорта.\nИспользуй текущую позицию пользователя и координаты первого найденного аэропорта.",
)
FINAL_TASK = text_block(
    _PROMPTS.get("final_task"),
    "Сформируй финальный ответ пользователю по найденному аэропорту и маршруту. Пиши по-русски.",
)
SCENARIO_CONTEXT = text_block(
    _PROMPTS.get("scenario_context"),
    "Пользователь хочет найти ближайший аэропорт и построить маршрут.",
)
SEARCH_TOOL_SCHEMA = dict_value(
    _SCHEMAS.get("search_tool_schema"),
    {
        "parameters": {
            "city": {"type": "string", "description": "Город для поиска ближайших аэропортов"},
            "radius_km": {"type": "number", "description": "Радиус поиска в километрах", "default": 50},
        }
    },
)
ROUTE_TOOL_SCHEMA = dict_value(
    _SCHEMAS.get("route_tool_schema"),
    {
        "parameters": {
            "from_lat": {"type": "number"},
            "from_lon": {"type": "number"},
            "to_lat": {"type": "number"},
            "to_lon": {"type": "number"},
        }
    },
)


def _to_float(value: Any) -> float | None:
    """Пытается привести входное значение к float; иначе возвращает None."""
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except Exception:
            return None
    return None


def _normalize_route_args(extracted: dict[str, Any], pos_data: dict[str, Any], airports_data: dict[str, Any]) -> dict[str, float] | None:
    """Собирает полный набор координат маршрута из LLM-параметров и данных tools."""
    out: dict[str, float] = {}
    for key in ("from_lat", "from_lon", "to_lat", "to_lon"):
        val = _to_float(extracted.get(key))
        if val is not None:
            out[key] = val
    if "from_lat" not in out and _to_float(pos_data.get("lat")) is not None:
        out["from_lat"] = _to_float(pos_data["lat"])  # type: ignore[index]
    if "from_lon" not in out and _to_float(pos_data.get("lon")) is not None:
        out["from_lon"] = _to_float(pos_data["lon"])  # type: ignore[index]
    # Fill missing destination from the first candidate airport returned by search tool.
    airports = airports_data.get("airports") if isinstance(airports_data.get("airports"), list) else []
    first = airports[0] if airports and isinstance(airports[0], dict) else {}
    if "to_lat" not in out and _to_float(first.get("lat")) is not None:
        out["to_lat"] = _to_float(first["lat"])  # type: ignore[index]
    if "to_lon" not in out and _to_float(first.get("lon")) is not None:
        out["to_lon"] = _to_float(first["lon"])  # type: ignore[index]
    required = ("from_lat", "from_lon", "to_lat", "to_lon")
    return {k: out[k] for k in required} if all(k in out for k in required) else None


async def run_find_nearest_airport(req: WorkflowRunRequest, io: RuntimeIO) -> WorkflowRunResponse:
    """Ищет ближайший аэропорт и строит маршрут через цепочку из 3 tools + 3 LLM вызовов."""
    pos_resp = await io.call_tool(parent=req, tool_name=TOOL_GET_POSITION, args={})
    if not pos_resp.ok:
        return failed_response(req, code=(pos_resp.error.code if pos_resp.error else "tool_failed"), message="Не удалось получить текущую позицию.", runtime=next_runtime(req))

    tool_results = [{"tool_name": TOOL_GET_POSITION, "result": pos_resp.data}]
    search_params_resp = await io.call_llm(
        parent=req,
        mode="tool_params",
        input_data={"task": SEARCH_PARAMS_TASK, "user_message": req.text, "tool_name": TOOL_SEARCH_AIRPORTS, "tool_schema": SEARCH_TOOL_SCHEMA, "tool_results": tool_results},
        constraints={"temperature": 0},
    )
    search_params = normalize_tool_params(search_params_resp).get("extracted") or {}
    city = str(search_params.get("city") or "").strip() if isinstance(search_params, dict) else ""
    radius_km = _to_float(search_params.get("radius_km")) if isinstance(search_params, dict) else None
    pos_data = extract_nested_data(pos_resp.data) or {}
    if not city:
        city = str(pos_data.get("city") or DEFAULT_CITY).strip() or DEFAULT_CITY
    search_resp = await io.call_tool(
        parent=req,
        tool_name=TOOL_SEARCH_AIRPORTS,
        args={"city": city, "radius_km": radius_km if radius_km is not None else DEFAULT_RADIUS_KM},
    )
    if not search_resp.ok:
        return failed_response(req, code=(search_resp.error.code if search_resp.error else "tool_failed"), message="Не удалось найти ближайшие аэропорты.", runtime=next_runtime(req))

    tool_results.append({"tool_name": TOOL_SEARCH_AIRPORTS, "result": search_resp.data})
    route_params_resp = await io.call_llm(
        parent=req,
        mode="tool_params",
        input_data={"task": ROUTE_PARAMS_TASK, "user_message": req.text, "tool_name": TOOL_BUILD_ROUTE, "tool_schema": ROUTE_TOOL_SCHEMA, "tool_results": tool_results},
        constraints={"temperature": 0},
    )
    route_params = normalize_tool_params(route_params_resp).get("extracted") or {}
    airports_data = extract_nested_data(search_resp.data) or {}
    route_args = _normalize_route_args(route_params if isinstance(route_params, dict) else {}, pos_data, airports_data)
    if route_args is None:
        return failed_response(req, code="route_params_missing", message="Не удалось собрать координаты для маршрута.", runtime=next_runtime(req))

    route_resp = await io.call_tool(parent=req, tool_name=TOOL_BUILD_ROUTE, args=route_args)
    if not route_resp.ok:
        return failed_response(req, code=(route_resp.error.code if route_resp.error else "tool_failed"), message="Не удалось построить маршрут.", runtime=next_runtime(req))

    tool_results.append({"tool_name": TOOL_BUILD_ROUTE, "result": route_resp.data})
    final_resp = await io.call_llm(
        parent=req,
        mode="final_response",
        input_data={"task": FINAL_TASK, "user_message": req.text, "tool_results": tool_results, "scenario_context": SCENARIO_CONTEXT},
        constraints={"temperature": 0.1},
    )
    message = extract_llm_text(final_resp) or "Маршрут построен."
    route_data = extract_nested_data(route_resp.data) or {}
    client_events = [
        {"command": "SET_POSITION", "payload": {"data": {"current_position": pos_data}}},
        {"command": "SET_AIRPORTS", "payload": {"data": {"airports": airports_data.get("airports", [])}}},
        {"command": "BUILD_ROUTE", "payload": {"data": {"route": route_data}}},
    ]
    return done_response(req, message, client_events=client_events)
