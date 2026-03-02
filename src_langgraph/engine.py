from __future__ import annotations

from typing import Any
from uuid import uuid4

from langgraph.graph import END, StateGraph

from src_shared.contracts import WorkflowRunRequest, WorkflowRunResponse

from src_langgraph.memory import (
    append_exchange,
    compact_memory,
    context_with_memory,
    prepare_dialog_memory,
    response_message_text,
)
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
    """LangGraph engine: scenario dispatch + stateful response post-processing."""

    def __init__(
        self,
        io: RuntimeIO,
        *,
        memory_recent_messages: int = 16,
        memory_summary_max_chars: int = 4000,
        memory_context_max_chars: int = 5000,
    ) -> None:
        self.io = io
        self.memory_recent_messages = max(2, int(memory_recent_messages))
        self.memory_summary_max_chars = max(200, int(memory_summary_max_chars))
        self.memory_context_max_chars = max(300, int(memory_context_max_chars))
        self._graph = self._build_graph()

    def _build_graph(self):
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
        user_turn_id = req.turn_id.strip() if isinstance(req.turn_id, str) and req.turn_id.strip() else str(uuid4())
        assistant_turn_id = str(uuid4())
        req_with_turn = req.model_copy(update={"turn_id": user_turn_id})

        memory = prepare_dialog_memory(
            req=req_with_turn,
            recent_messages_limit=self.memory_recent_messages,
            summary_max_chars=self.memory_summary_max_chars,
            context_max_chars=self.memory_context_max_chars,
        )
        state = await self._graph.ainvoke(
            {
                "req": req_with_turn,
                "summary": memory["summary"],
                "history": memory["recent_turns"],
                "dialog_context": memory["dialog_context"],
                "context_extra": memory["context_extra"],
                "user_turn_id": user_turn_id,
                "assistant_turn_id": assistant_turn_id,
            }
        )
        resp = state.get("response")
        if not isinstance(resp, WorkflowRunResponse):
            raise RuntimeError("workflow did not produce WorkflowRunResponse")
        return self._finalize_response(state, resp)

    def _finalize_response(self, state: FlowState, resp: WorkflowRunResponse) -> WorkflowRunResponse:
        summary = str(state.get("summary") or "").strip()
        history_raw = state.get("history")
        history = history_raw if isinstance(history_raw, list) else []
        context_extra = state.get("context_extra")
        context_extra = context_extra if isinstance(context_extra, dict) else {}
        user_turn_id = str(state.get("user_turn_id") or "").strip() or str(uuid4())
        assistant_turn_id = str(state.get("assistant_turn_id") or "").strip() or str(uuid4())
        assistant_text = response_message_text(resp)

        updated_history = append_exchange(
            recent_turns=history,
            user_turn_id=user_turn_id,
            user_text=str(state["req"].text),
            assistant_turn_id=assistant_turn_id,
            assistant_text=assistant_text,
        )
        next_summary, next_recent = compact_memory(
            summary=summary,
            recent_turns=updated_history,
            recent_messages_limit=self.memory_recent_messages,
            summary_max_chars=self.memory_summary_max_chars,
        )
        next_runtime = resp.next_runtime.model_copy(
            update={"context": context_with_memory(summary=next_summary, recent_turns=next_recent, extra=context_extra)}
        )
        with_runtime = resp.model_copy(update={"next_runtime": next_runtime})
        return self._with_turn_ids(with_runtime, user_turn_id=user_turn_id, assistant_turn_id=assistant_turn_id)

    @staticmethod
    def _with_turn_ids(resp: WorkflowRunResponse, *, user_turn_id: str, assistant_turn_id: str) -> WorkflowRunResponse:
        handler = resp.client_handler if isinstance(resp.client_handler, dict) else {}
        command = handler.get("command") if isinstance(handler.get("command"), str) else ""
        if not command and resp.status == "FAILED":
            handler = {
                "command": "SHOW_ERROR_MESSAGE",
                "payload": {"message": response_message_text(resp) or "Request failed."},
            }
        elif not command:
            return resp

        payload = handler.get("payload") if isinstance(handler.get("payload"), dict) else {}
        payload = dict(payload)
        payload.setdefault("user_turn_id", user_turn_id)
        payload.setdefault("assistant_turn_id", assistant_turn_id)
        next_handler = dict(handler)
        next_handler["payload"] = payload
        return resp.model_copy(update={"client_handler": next_handler})

    def _route_after_dispatch(self, state: FlowState) -> str:
        scenario_id = str(state.get("selected_scenario") or "").strip()
        return scenario_id if scenario_id in SUPPORTED_SCENARIOS else SC_FREE_SPEECH

    async def _node_dispatch(self, state: FlowState) -> dict[str, Any]:
        req = state["req"]
        pending = req.runtime.pending if isinstance(req.runtime.pending, dict) else None
        active = (req.runtime.active_workflow_id or "").strip()
        if active == SC_WHERE_MY_FLIGHT and pending:
            return {"selected_scenario": SC_WHERE_MY_FLIGHT}
        scenario, routing = await choose_scenario(req, self.io, dialog_context=str(state.get("dialog_context") or ""))
        return {"selected_scenario": scenario, "routing": routing}

    async def _node_scenario_echo(self, state: FlowState) -> dict[str, WorkflowRunResponse]:
        return {"response": await run_echo(state["req"])}

    async def _node_where_my_flight(self, state: FlowState) -> dict[str, WorkflowRunResponse]:
        return {"response": await run_where_my_flight(state["req"], self.io, dialog_context=str(state.get("dialog_context") or ""))}

    async def _node_find_nearest_airport(self, state: FlowState) -> dict[str, WorkflowRunResponse]:
        return {
            "response": await run_find_nearest_airport(
                state["req"],
                self.io,
                dialog_context=str(state.get("dialog_context") or ""),
            )
        }

    async def _node_free_speech(self, state: FlowState) -> dict[str, WorkflowRunResponse]:
        return {"response": await run_free_speech(state["req"], self.io, dialog_context=str(state.get("dialog_context") or ""))}
