from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict

from src_agent.utils.mcp_tools import AgentClientHandler


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


class Scenario:
    id = "base"
    title = "Base"
    description = "Base scenario."
    input_hints: Dict[str, str] = {}
    input_types: Dict[str, str] = {}

    def on_user_turn(self, state: Dict[str, Any], prompt: str, turn_id: str) -> None:
        self._log(state, status="RUNNING", kind="USER_TURN", data={"text": prompt}, turn_id=turn_id)

    def maybe_switch(self, state: Dict[str, Any], prompt: str) -> str | None:
        return None

    def display_request(
        self,
        state: Dict[str, Any],
        *,
        field: str,
        prompt_text: str,
        validation_hint: str,
        validation_regex: str | None = None,
        turn_id: str,
    ) -> AgentClientHandler:
        artifact_name = f"{self.id}.request.{field}.{turn_id}"
        artifact = {
            "field": field,
            "prompt": prompt_text,
            "hint": validation_hint,
        }
        self._store_artifact(state, name=artifact_name, data=artifact)
        self._log(
            state,
            status="NEEDS_INPUT",
            kind="ASK_INPUT",
            data={"field": field, "prompt": prompt_text},
            turn_id=turn_id,
        )
        if isinstance(state.get("scenario"), dict):
            state["scenario"]["status"] = "NEEDS_INPUT"
        state["pending"] = {
            "scenario_id": self.id,
            "kind": "input",
            "field": field,
            "prompt": prompt_text,
            "hint": validation_hint,
            "validation_regex": validation_regex,
        }
        return {
            "command": "ASK_USER_INPUT",
            "artifacts": {
                "last": artifact_name,
                "all": [artifact_name],
                "payload": {artifact_name: artifact},
            },
        }

    def display_result(
        self,
        state: Dict[str, Any],
        *,
        result_artifact_name: str,
        summary_text: str,
        data: Dict[str, Any] | None,
        turn_id: str,
        command: str = "SHOW_MESSAGE",
    ) -> AgentClientHandler:
        artifact_name = (
            result_artifact_name
            if result_artifact_name.startswith(f"{self.id}.")
            else f"{self.id}.result.{result_artifact_name}"
        )
        artifact: Dict[str, Any] = {"summary": summary_text}
        if data is not None:
            artifact["data"] = data
        self._store_artifact(state, name=artifact_name, data=artifact)
        self._log(
            state,
            status="DONE",
            kind="RESULT_READY",
            data={"artifact": artifact_name},
            turn_id=turn_id,
        )
        if isinstance(state.get("scenario"), dict):
            state["scenario"]["status"] = "DONE"
        if isinstance(state.get("pending"), dict) and state["pending"].get("scenario_id") == self.id:
            state["pending"] = None
        return {
            "command": command,
            "artifacts": {
                "last": artifact_name,
                "all": [artifact_name],
                "payload": {artifact_name: artifact},
            },
        }

    def _store_artifact(
        self,
        state: Dict[str, Any],
        *,
        name: str,
        data: Dict[str, Any],
    ) -> None:
        scenarios = state.setdefault("scenario_artifacts", {})
        scenario_store = scenarios.get(self.id)
        if scenario_store is None:
            scenario_store = {}
            scenarios[self.id] = scenario_store
        if not isinstance(scenario_store, dict):
            raise RuntimeError("Invalid scenario_artifacts storage type")
        if name in scenario_store:
            raise RuntimeError(f"Artifact key collision: {self.id}.{name}")
        scenario_store[name] = data

    def _log(
        self,
        state: Dict[str, Any],
        *,
        status: str,
        kind: str,
        data: Dict[str, Any],
        turn_id: str | None,
    ) -> None:
        state.setdefault("scenario_log", []).append({
            "ts": _now_iso(),
            "scenario_id": self.id,
            "status": status,
            "kind": kind,
            "data": data,
            "turn_id": turn_id,
        })
