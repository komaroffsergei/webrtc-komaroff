from __future__ import annotations

import re
from typing import Any

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


async def choose_scenario(req: WorkflowRunRequest, io: RuntimeIO) -> tuple[str, dict[str, Any]]:
    """Выбирает сценарий через fast-path или LLM router и отдает routing-метаданные."""
    # Fast path for explicit local command; no LLM call needed.
    if is_explicit_echo(req.text):
        return SC_ECHO, {}

    llm_resp = await io.call_llm(
        parent=req,
        mode="routing_decision",
        input_data={"task": ROUTER_TASK, "text": req.text, "available_scenarios": ROUTER_SCENARIOS},
        constraints={"temperature": 0},
    )
    if not llm_resp.ok or not isinstance(llm_resp.data, dict):
        return SC_FREE_SPEECH, {}

    data = dict(llm_resp.data)
    candidate = str(data.get("workflow_id") or "").strip()
    if candidate == SC_WHERE_MY_FLIGHT:
        return SC_WHERE_MY_FLIGHT, data
    if candidate == SC_FIND_NEAREST_AIRPORT:
        return SC_FIND_NEAREST_AIRPORT, data
    if candidate == SC_FREE_SPEECH:
        return SC_FREE_SPEECH, data
    if candidate == SC_ECHO and is_explicit_echo(req.text):
        return SC_ECHO, data
    # Unknown/invalid router output always degrades to free speech.
    return SC_FREE_SPEECH, data
