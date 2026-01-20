from __future__ import annotations

from typing import Any, Dict

from src_agent.scenarios.base import Scenario
from src_agent.tools.tools import get_artifact_by_key, get_open_airports, tool_context
from src_agent.utils.db import add_turn


class ListAirportsOpenScenario(Scenario):
    id = "list_airports_open"
    title = "List open airports"
    description = "Returns airports with status=open from airports.json."

    async def handle(
        self,
        state: Dict[str, Any],
        *,
        prompt: str,
        turn_id: str,
        session_id: str,
        db,
        llm_request=None,
        request_id: str,
    ):
        self.on_user_turn(state, prompt, turn_id)

        with tool_context(state, self.id):
            _, res = get_open_airports()
            key = res.get("artifact_key") if isinstance(res, dict) else None
            if res.get("status") != "ok" or not isinstance(key, str):
                error_text = res.get("message") if isinstance(res, dict) else None
                error_text = str(error_text) if error_text else "Failed to fetch open airports."
                handler = self.display_result(
                    state,
                    result_artifact_name="error",
                    summary_text=error_text,
                    data={"error": res},
                    turn_id=turn_id,
                    command="SHOW_ERROR_MESSAGE",
                )
                add_turn(state, role="assistant", text=error_text)
                return {"success": True, "result": error_text, "client_handler": handler}

            artifact = get_artifact_by_key(key)

        airports = (artifact.get("data") or {}).get("airports") if isinstance(artifact, dict) else None
        count = len(airports) if isinstance(airports, list) else 0
        summary = f"Found {count} open airports."
        handler = {
            "command": "SHOW_AIRPORTS",
            "artifacts": {
                "last": key,
                "all": [key],
                "payload": {key: artifact},
            },
        }
        add_turn(state, role="assistant", text=summary)
        return {"success": True, "result": summary, "client_handler": handler}

