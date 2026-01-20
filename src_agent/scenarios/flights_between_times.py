from __future__ import annotations

import re
from typing import Any, Dict, Optional, Tuple

from src_agent.scenarios.base import Scenario
from src_agent.settings import (
    FLIGHTS_BETWEEN_TIMES_UNAVAILABLE_TEMPLATE,
    SCENARIO_FLIGHTS_BETWEEN_TIMES_DESC,
    SCENARIO_FLIGHTS_BETWEEN_TIMES_TITLE,
)
from src_agent.utils.db import add_turn


class FlightsBetweenTimesScenario(Scenario):
    id = "flights_between_times"
    title = SCENARIO_FLIGHTS_BETWEEN_TIMES_TITLE
    description = SCENARIO_FLIGHTS_BETWEEN_TIMES_DESC
    input_hints = {
        "start_time": "Время начала, формат HH:MM.",
        "end_time": "Время окончания, формат HH:MM.",
    }
    input_types = {"start_time": "string", "end_time": "string"}

    _time_re = re.compile(r"\b([01]?\d|2[0-3])(?::([0-5]\d))?\b")

    async def handle(
        self,
        state: Dict[str, Any],
        *,
        prompt: str,
        turn_id: str,
        session_id: str,
        db,
        llm_request,
        request_id: str,
    ):
        self.on_user_turn(state, prompt, turn_id)

        scenario_input = (state.get("scenario") or {}).get("input") or {}
        pending = state.get("pending")
        if isinstance(pending, dict) and pending.get("scenario_id") == self.id and pending.get("field") == "time_range":
            start_time, end_time = self._extract_time_range(prompt)
            if not start_time or not end_time:
                self._log(
                    state,
                    status="NEEDS_INPUT",
                    kind="INPUT_INVALID",
                    data={"field": "time_range", "text": prompt},
                    turn_id=turn_id,
                )
                return await self._ask_time_range(state, turn_id, llm_request=llm_request, user_text=prompt, invalid=True)
            state["pending"] = None
            return self._respond_placeholder(state, turn_id, start_time, end_time)

        start_time = scenario_input.get("start_time")
        end_time = scenario_input.get("end_time")
        if not isinstance(start_time, str) or not isinstance(end_time, str):
            start_time, end_time = self._extract_time_range(prompt)
        if not start_time or not end_time:
            return await self._ask_time_range(state, turn_id, llm_request=llm_request, user_text=prompt, invalid=False)

        return self._respond_placeholder(state, turn_id, start_time, end_time)

    def _extract_time_range(self, prompt: str) -> Tuple[Optional[str], Optional[str]]:
        matches = [m for m in self._time_re.finditer(prompt or "")]
        if len(matches) < 2:
            return None, None
        start = self._format_time(matches[0])
        end = self._format_time(matches[1])
        return start, end

    def _format_time(self, match: re.Match) -> str:
        hour = match.group(1)
        minute = match.group(2) or "00"
        return f"{hour.zfill(2)}:{minute}"

    async def _ask_time_range(self, state: Dict[str, Any], turn_id: str, *, llm_request, user_text: str, invalid: bool):
        meta = {
            "reason": "missing_required_parameter",
            "scenario_id": self.id,
            "missing": ["start_time", "end_time"],
            "constraints": {"start_time": "time like 12:00", "end_time": "time like 16:00"},
            "previous_invalid": invalid,
        }
        try:
            question = await self.build_clarification_question(llm_request=llm_request, user_text=user_text, meta=meta)
        except Exception as exc:
            error_text = f"Unable to ask for clarification: {exc}"
            handler = self.display_result(
                state,
                result_artifact_name="error",
                summary_text=error_text,
                data={"error": str(exc)},
                turn_id=turn_id,
                command="SHOW_ERROR_MESSAGE",
            )
            add_turn(state, role="assistant", text=error_text)
            return {"success": True, "result": error_text, "client_handler": handler}

        handler = self.display_request(
            state,
            field="time_range",
            prompt_text=question,
            validation_hint="",
            validation_regex=None,
            meta=meta,
            turn_id=turn_id,
        )
        add_turn(state, role="assistant", text=question)
        return {"success": True, "result": question, "client_handler": handler}

    def _respond_placeholder(self, state: Dict[str, Any], turn_id: str, start: str, end: str):
        summary = FLIGHTS_BETWEEN_TIMES_UNAVAILABLE_TEMPLATE.format(start=start, end=end)
        handler = self.display_result(
            state,
            result_artifact_name="flights_between_times",
            summary_text=summary,
            data={"start_time": start, "end_time": end},
            turn_id=turn_id,
        )
        add_turn(state, role="assistant", text=summary)
        return {
            "success": True,
            "result": summary,
            "client_handler": handler,
        }
