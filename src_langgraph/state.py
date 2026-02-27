from __future__ import annotations

from typing import Any, TypedDict

from src_shared.contracts import WorkflowRunRequest, WorkflowRunResponse

SC_ECHO = "echo@2.0.0"
SC_WHERE_MY_FLIGHT = "where_my_flight@2.0.0"
SC_FIND_NEAREST_AIRPORT = "find_nearest_airport@2.0.0"
SC_FREE_SPEECH = "free_speech@2.0.0"

SUPPORTED_SCENARIOS = {
    SC_ECHO,
    SC_WHERE_MY_FLIGHT,
    SC_FIND_NEAREST_AIRPORT,
    SC_FREE_SPEECH,
}


class FlowState(TypedDict, total=False):
    """Состояние исполнения графа для одного запроса."""
    req: WorkflowRunRequest
    selected_scenario: str
    routing: dict[str, Any]
    response: WorkflowRunResponse
