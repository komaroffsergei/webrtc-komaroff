from __future__ import annotations

from src_shared.contracts import WorkflowRunRequest, WorkflowRunResponse

from src_langgraph.config_loader import dict_value, load_config, text_block
from src_langgraph.responses import done_response, failed_response, partial_response, next_runtime
from src_langgraph.runtime_io import RuntimeIO
from src_langgraph.scenarios.common import (
    extract_llm_text,
    extract_nested_data,
    merge_non_empty_params,
    normalize_tool_params,
)
from src_langgraph.state import SC_WHERE_MY_FLIGHT

_CFG = load_config("where_my_flight")
_PROMPTS = dict_value(_CFG.get("prompts"))
_TOOLS = dict_value(_CFG.get("tools"))
_SCHEMAS = dict_value(_CFG.get("schemas"))

TOOL_NAME = str(_TOOLS.get("status") or "get_flight_status")
TOOL_PARAMS_TASK = text_block(
    _PROMPTS.get("tool_params_task"),
    (
        "Определи параметры для поиска статуса рейса.\n"
        "Если параметров не хватает, верни missing и задай пользователю уточняющий вопрос на русском.\n"
        "Если параметр распознан как номер рейса — нормализуй его (удали пробелы внутри номера рейса)."
    ),
)
FINAL_TASK = text_block(
    _PROMPTS.get("final_task"),
    "Сформируй понятный ответ пользователю по результату поиска рейса. Пиши по-русски.",
)
SCENARIO_CONTEXT = text_block(
    _PROMPTS.get("scenario_context"),
    "Пользователь хочет узнать статус рейса. Ответ должен быть кратким и на русском языке.",
)
ASK_INPUT_DEFAULT = text_block(
    _PROMPTS.get("ask_input_default"),
    "Укажите номер рейса (например, SU123) или фамилию пассажира.",
)
TOOL_SCHEMA = dict_value(
    _SCHEMAS.get("status_tool_schema"),
    {
        "parameters": {
            "flight_number": {"type": "string", "description": "Номер рейса, например SU123"},
            "last_name": {"type": "string", "description": "Фамилия пассажира"},
        }
    },
)


def _format_flight_message(tool_data: dict) -> str:
    """Строит fallback-текст по данным инструмента, если финальный LLM ответ пустой."""
    data = extract_nested_data(tool_data) or {}
    flight = data.get("flight") if isinstance(data.get("flight"), dict) else {}
    if not flight:
        return "Статус рейса не найден."
    fn = str(flight.get("flight_number") or "рейс").strip()
    src = str(flight.get("from") or "?").strip()
    dst = str(flight.get("to") or "?").strip()
    dep = str(flight.get("departure_time") or "").strip()
    arr = str(flight.get("arrival_time") or "").strip()
    status = str(flight.get("status") or "").strip().upper()
    dep_short = dep[11:16] if len(dep) >= 16 and "T" in dep else dep
    arr_short = arr[11:16] if len(arr) >= 16 and "T" in arr else arr
    status_map = {"ON_TIME": "вовремя", "DELAYED": "задерживается", "CANCELLED": "отменен"}
    return f"Рейс {fn} ({src} → {dst}), вылет {dep_short}, прибытие {arr_short}. Статус: {status_map.get(status, status.lower() or 'неизвестен')}."


async def run_where_my_flight(req: WorkflowRunRequest, io: RuntimeIO) -> WorkflowRunResponse:
    """Обрабатывает сценарий статуса рейса с поддержкой мультитурового сбора параметров."""
    pending = req.runtime.pending if isinstance(req.runtime.pending, dict) else {}
    prev = pending.get("extracted") if isinstance(pending.get("extracted"), dict) else {}

    params_resp = await io.call_llm(
        parent=req,
        mode="tool_params",
        input_data={"task": TOOL_PARAMS_TASK, "user_message": req.text, "tool_name": TOOL_NAME, "tool_schema": TOOL_SCHEMA},
        constraints={"temperature": 0},
    )
    parsed = normalize_tool_params(params_resp)
    # Merge params from previous turn with params extracted from the current user message.
    merged = merge_non_empty_params(prev, parsed["extracted"] if isinstance(parsed["extracted"], dict) else {})

    has_flight = isinstance(merged.get("flight_number"), str) and bool(str(merged["flight_number"]).strip())
    has_last = isinstance(merged.get("last_name"), str) and bool(str(merged["last_name"]).strip())
    if not (has_flight or has_last):
        prompt = str(parsed.get("prompt") or ASK_INPUT_DEFAULT).strip() or ASK_INPUT_DEFAULT
        pending_state = {
            "type": "tool_params",
            "scenario_id": SC_WHERE_MY_FLIGHT,
            "tool_name": TOOL_NAME,
            "extracted": merged,
            "missing": ["flight_number_or_last_name"],
            "prompt": prompt,
        }
        return partial_response(req, prompt, active_workflow_id=SC_WHERE_MY_FLIGHT, pending=pending_state)

    args: dict[str, str] = {}
    if has_flight:
        args["flight_number"] = str(merged["flight_number"]).strip()
    if has_last:
        args["last_name"] = str(merged["last_name"]).strip()

    tool_resp = await io.call_tool(parent=req, tool_name=TOOL_NAME, args=args)
    if not tool_resp.ok:
        code = tool_resp.error.code if tool_resp.error else "tool_failed"
        msg = "Статус рейса не найден." if code == "not_found" else "Не удалось получить статус рейса."
        if code == "not_found":
            return done_response(req, msg)
        return failed_response(
            req,
            code=code,
            message=msg,
            runtime=next_runtime(req),
            client_handler={"command": "SHOW_ERROR_MESSAGE", "payload": {"message": msg, "code": code}},
        )

    final_resp = await io.call_llm(
        parent=req,
        mode="final_response",
        input_data={
            "task": FINAL_TASK,
            "user_message": req.text,
            "tool_results": [{"tool_name": TOOL_NAME, "result": tool_resp.data}],
            "scenario_context": SCENARIO_CONTEXT,
        },
        constraints={"temperature": 0.1},
    )
    message = extract_llm_text(final_resp) or _format_flight_message(tool_resp.data or {})
    return done_response(req, message)
