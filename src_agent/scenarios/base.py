from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict

from src_agent.utils.mcp_tools import AgentClientHandler


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


class Scenario:
    id = "base"

    def matches(self, prompt: str) -> bool:
        return False

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
        turn_id: str,
    ) -> AgentClientHandler:
        artifact_name = f"{self.id}_request"
        artifact = {
            "field": field,
            "prompt": prompt_text,
            "hint": validation_hint,
        }
        self._store_artifact(state, name=artifact_name, data=artifact, turn_id=turn_id)
        self._log(
            state,
            status="NEEDS_INPUT",
            kind="ASK_INPUT",
            data={"field": field, "prompt": prompt_text},
            turn_id=turn_id,
        )
        if isinstance(state.get("scenario"), dict):
            state["scenario"]["status"] = "NEEDS_INPUT"
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
    ) -> AgentClientHandler:
        artifact: Dict[str, Any] = {"summary": summary_text}
        if data is not None:
            artifact["data"] = data
        self._store_artifact(state, name=result_artifact_name, data=artifact, turn_id=turn_id)
        self._log(
            state,
            status="DONE",
            kind="RESULT_READY",
            data={"artifact": result_artifact_name},
            turn_id=turn_id,
        )
        if isinstance(state.get("scenario"), dict):
            state["scenario"]["status"] = "DONE"
        return {
            "command": "SHOW_MESSAGE",
            "artifacts": {
                "last": result_artifact_name,
                "all": [result_artifact_name],
                "payload": {result_artifact_name: artifact},
            },
        }

    def _store_artifact(
        self,
        state: Dict[str, Any],
        *,
        name: str,
        data: Dict[str, Any],
        turn_id: str,
    ) -> None:
        state.setdefault("artifacts", []).append({
            "turn_id": turn_id,
            "scenario_id": self.id,
            "name": name,
            "data": data,
            "ts": _now_iso(),
        })

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
