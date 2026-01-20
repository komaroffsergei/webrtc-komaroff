from __future__ import annotations

from typing import Any, Dict

from src_agent.scenarios.base import Scenario
from src_agent.utils.db import add_turn


class AirportsClarifyScenario(Scenario):
    id = "airports_clarify"
    title = "Clarify airport request"
    description = "Asks the user to clarify what kind of airport data they need."

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

        pending = state.get("pending")
        if isinstance(pending, dict) and pending.get("scenario_id") == self.id and pending.get("field") == "airports_intent":
            choice = self._parse_choice(prompt)
            if not choice:
                return self._ask(state, turn_id, stronger=True)

            state["pending"] = None
            if isinstance(state.get("scenario"), dict):
                state["scenario"]["id"] = choice
                state["scenario"]["status"] = "RUNNING"
                state["scenario"]["input"] = None

            state.setdefault("scenario_artifacts", {}).pop(choice, None)

            from src_agent.scenarios.registry import get_scenario
            scenario = get_scenario(choice)
            if not scenario:
                error_text = f"Unknown scenario: {choice}"
                handler = self.display_result(
                    state,
                    result_artifact_name="error",
                    summary_text=error_text,
                    data={"scenario_id": choice},
                    turn_id=turn_id,
                    command="SHOW_ERROR_MESSAGE",
                )
                add_turn(state, role="assistant", text=error_text)
                return {"success": True, "result": error_text, "client_handler": handler}

            return await scenario.handle(
                state,
                prompt=prompt,
                turn_id=turn_id,
                session_id=session_id,
                db=db,
                llm_request=llm_request,
                request_id=request_id,
            )

        return self._ask(state, turn_id, stronger=False)

    def _ask(self, state: Dict[str, Any], turn_id: str, *, stronger: bool):
        prompt_text = "Уточните: ближайшие / все / открытые / закрытые / поиск. Ответьте одним словом."
        if stronger:
            prompt_text = "Ответьте одним словом: ближайшие / все / открытые / закрытые / поиск."

        handler = self.display_request(
            state,
            field="airports_intent",
            prompt_text=prompt_text,
            validation_hint="ближайшие | все | открытые | закрытые | поиск",
            validation_regex=r"^(ближайшие|все|открытые|закрытые|поиск)$",
            turn_id=turn_id,
        )
        add_turn(state, role="assistant", text=prompt_text)
        return {"success": True, "result": prompt_text, "client_handler": handler}

    def _parse_choice(self, text: str) -> str | None:
        v = (text or "").strip().lower()
        if v in ("nearest", "near", "nearby", "closest", "1", "ближайшие", "рядом"):
            return "nearest_airports"
        if v in ("all", "2", "все"):
            return "list_airports_all"
        if v in ("open", "3", "открытые"):
            return "list_airports_open"
        if v in ("closed", "4", "закрытые"):
            return "list_airports_closed"
        if v in ("search", "find", "5", "поиск"):
            return "search_airports_by_name_or_code"
        return None
