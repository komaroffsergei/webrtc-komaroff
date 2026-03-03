from __future__ import annotations

import re
from typing import Any, Iterable

from src_shared.contracts import WorkflowRunRequest

from src_langgraph.config_loader import list_of_dicts, load_config, text_block
from src_langgraph.runtime_io import RuntimeIO
from src_langgraph.state import (
    SC_ECHO,
    SC_FIND_NEAREST_AIRPORT,
    SC_FREE_SPEECH,
    SC_WHERE_MY_FLIGHT,
)

_ROUTER_CFG = load_config("router")
ROUTER_TASK = text_block(
    _ROUTER_CFG.get("task"),
    "Определи, какой сценарий лучше всего подходит для запроса пользователя. Выбирай только один сценарий из списка.",
)
ROUTER_SCENARIOS = list_of_dicts(
    _ROUTER_CFG.get("available_scenarios"),
    [
        {"id": SC_WHERE_MY_FLIGHT, "description": "Найти статус рейса по номеру рейса или фамилии пассажира"},
        {"id": SC_FIND_NEAREST_AIRPORT, "description": "Найти ближайший аэропорт и построить маршрут до него"},
        {"id": SC_FREE_SPEECH, "description": "Свободный разговор: общение с пользователем без инструментов"},
    ],
)


def is_explicit_echo(text: str) -> bool:
    """Проверяет, что пользователь явно вызвал локальную команду echo/эхо."""
    return bool(re.match(r"^\s*(echo|эхо)\b", text or "", flags=re.IGNORECASE))


def parse_echo_payload(text: str) -> str:
    """Удаляет префикс echo/эхо и возвращает полезную часть сообщения."""
    stripped = str(text or "").strip()
    return re.sub(r"^\s*(echo|эхо)\b[:\s-]*", "", stripped, flags=re.IGNORECASE).strip()


def _excluded_set(excluded_scenarios: Iterable[str] | None) -> set[str]:
    return {str(x).strip() for x in (excluded_scenarios or []) if str(x).strip()}


def _filtered_scenarios(excluded_scenarios: Iterable[str] | None) -> list[dict[str, str]]:
    excluded = _excluded_set(excluded_scenarios)
    out: list[dict[str, str]] = []
    for row in ROUTER_SCENARIOS:
        if not isinstance(row, dict):
            continue
        scenario_id = str(row.get("id") or "").strip()
        if not scenario_id or scenario_id in excluded:
            continue
        out.append({"id": scenario_id, "description": str(row.get("description") or "").strip()})
    return out


async def choose_scenario(
    req: WorkflowRunRequest,
    io: RuntimeIO,
    *,
    dialog_context: str = "",
    excluded_scenarios: Iterable[str] | None = None,
    context_artifacts: dict[str, Any] | None = None,
) -> tuple[str, dict[str, Any]]:
    """Выбирает сценарий через fast-path или LLM router и отдает routing-метаданные."""
    excluded = _excluded_set(excluded_scenarios)
    scenarios = _filtered_scenarios(excluded_scenarios)
    allowed_ids = {str(x.get("id") or "").strip() for x in scenarios if isinstance(x, dict)}
    if not scenarios:
        return SC_FREE_SPEECH, {"reason": "No scenarios available after exclusions"}

    # Fast path for explicit local command; no LLM call needed.
    if is_explicit_echo(req.text) and SC_ECHO not in excluded:
        return SC_ECHO, {}

    llm_input: dict[str, Any] = {
        "task": ROUTER_TASK,
        "text": req.text,
        "available_scenarios": scenarios,
        "dialog_context": dialog_context,
    }
    if isinstance(context_artifacts, dict) and context_artifacts:
        llm_input["context_artifacts"] = context_artifacts

    llm_resp = await io.call_llm(
        parent=req,
        mode="routing_decision",
        input_data=llm_input,
        constraints={"temperature": 0},
    )
    if not llm_resp.ok or not isinstance(llm_resp.data, dict):
        return SC_FREE_SPEECH, {}

    data = dict(llm_resp.data)
    candidate = str(data.get("workflow_id") or "").strip()
    if candidate == SC_WHERE_MY_FLIGHT and candidate in allowed_ids:
        return SC_WHERE_MY_FLIGHT, data
    if candidate == SC_FIND_NEAREST_AIRPORT and candidate in allowed_ids:
        return SC_FIND_NEAREST_AIRPORT, data
    if candidate == SC_FREE_SPEECH and candidate in allowed_ids:
        return SC_FREE_SPEECH, data
    if candidate == SC_ECHO and SC_ECHO not in excluded and is_explicit_echo(req.text):
        return SC_ECHO, data
    # Unknown/invalid router output always degrades to free speech.
    return SC_FREE_SPEECH, data
