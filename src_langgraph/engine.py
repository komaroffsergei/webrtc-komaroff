from __future__ import annotations

from typing import Any

from langgraph.graph import END, StateGraph

from src_shared.contracts import WorkflowRunRequest, WorkflowRunResponse

from src_langgraph.router import choose_scenario
from src_langgraph.runtime_io import RuntimeIO
from src_langgraph.scenarios import (
    run_echo,
    run_find_nearest_airport,
    run_free_speech,
    run_where_my_flight,
)
from src_langgraph.state import (
    FlowState,
    SC_ECHO,
    SC_FIND_NEAREST_AIRPORT,
    SC_FREE_SPEECH,
    SC_WHERE_MY_FLIGHT,
    SUPPORTED_SCENARIOS,
)


class WorkflowEngine:
    """LangGraph-движок: dispatch + исполнение узлов сценариев."""

    def __init__(self, io: RuntimeIO) -> None:
        """Инициализирует I/O слой и компилирует граф один раз при старте."""
        self.io = io
        self._graph = self._build_graph()

    def _build_graph(self):
        """Строит граф маршрутизации между узлами сценариев."""
        builder = StateGraph(FlowState)
        builder.add_node("dispatch", self._node_dispatch)
        builder.add_node("scenario_echo", self._node_scenario_echo)
        builder.add_node("scenario_where_my_flight", self._node_where_my_flight)
        builder.add_node("scenario_find_nearest_airport", self._node_find_nearest_airport)
        builder.add_node("scenario_free_speech", self._node_free_speech)

        builder.set_entry_point("dispatch")
        builder.add_conditional_edges(
            "dispatch",
            self._route_after_dispatch,
            {
                SC_ECHO: "scenario_echo",
                SC_WHERE_MY_FLIGHT: "scenario_where_my_flight",
                SC_FIND_NEAREST_AIRPORT: "scenario_find_nearest_airport",
                SC_FREE_SPEECH: "scenario_free_speech",
            },
        )
        builder.add_edge("scenario_echo", END)
        builder.add_edge("scenario_where_my_flight", END)
        builder.add_edge("scenario_find_nearest_airport", END)
        builder.add_edge("scenario_free_speech", END)
        return builder.compile()

    async def run(self, req: WorkflowRunRequest) -> WorkflowRunResponse:
        """Выполняет граф для одного запроса и возвращает строго типизированный ответ."""
        state = await self._graph.ainvoke({"req": req})
        resp = state.get("response")
        if not isinstance(resp, WorkflowRunResponse):
            raise RuntimeError("workflow did not produce WorkflowRunResponse")
        return resp

    def _route_after_dispatch(self, state: FlowState) -> str:
        """Преобразует выбранный сценарий в имя следующего узла графа."""
        scenario_id = str(state.get("selected_scenario") or "").strip()
        return scenario_id if scenario_id in SUPPORTED_SCENARIOS else SC_FREE_SPEECH

    async def _node_dispatch(self, state: FlowState) -> dict[str, Any]:
        """Выбирает сценарий: продолжает pending-диалог или вызывает LLM-роутер."""
        req = state["req"]
        pending = req.runtime.pending if isinstance(req.runtime.pending, dict) else None
        active = (req.runtime.active_workflow_id or "").strip()
        # Keep user inside the same scenario while we are waiting for missing params.
        if active == SC_WHERE_MY_FLIGHT and pending:
            return {"selected_scenario": SC_WHERE_MY_FLIGHT}
        scenario, routing = await choose_scenario(req, self.io)
        return {"selected_scenario": scenario, "routing": routing}

    async def _node_scenario_echo(self, state: FlowState) -> dict[str, WorkflowRunResponse]:
        """Узел выполнения сценария echo."""
        return {"response": await run_echo(state["req"])}

    async def _node_where_my_flight(self, state: FlowState) -> dict[str, WorkflowRunResponse]:
        """Узел выполнения сценария where_my_flight."""
        return {"response": await run_where_my_flight(state["req"], self.io)}

    async def _node_find_nearest_airport(self, state: FlowState) -> dict[str, WorkflowRunResponse]:
        """Узел выполнения сценария find_nearest_airport."""
        return {"response": await run_find_nearest_airport(state["req"], self.io)}

    async def _node_free_speech(self, state: FlowState) -> dict[str, WorkflowRunResponse]:
        """Узел выполнения сценария free_speech."""
        return {"response": await run_free_speech(state["req"], self.io)}
