from __future__ import annotations

import re
from typing import Any, Dict, Optional, Tuple

from src_agent.scenarios.base import Scenario
from src_agent.settings import (
    FLIGHTS_BETWEEN_TIMES_UNAVAILABLE_TEMPLATE,
    HINT_TIME_RANGE,
    HINT_TIME_RANGE_STRONG,
    PROMPT_TIME_RANGE,
    PROMPT_TIME_RANGE_STRONG,
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
        llm_request=None,
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
                return self._ask_time_range(state, turn_id, stronger=True)
            state["pending"] = None
            return self._respond_placeholder(state, turn_id, start_time, end_time)

        start_time = scenario_input.get("start_time")
        end_time = scenario_input.get("end_time")
        if not isinstance(start_time, str) or not isinstance(end_time, str):
            start_time, end_time = self._extract_time_range(prompt)
        if not start_time or not end_time:
            return self._ask_time_range(state, turn_id, stronger=False)

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

    def _ask_time_range(self, state: Dict[str, Any], turn_id: str, *, stronger: bool):
        prompt_text = PROMPT_TIME_RANGE
        hint = HINT_TIME_RANGE
        if stronger:
            prompt_text = PROMPT_TIME_RANGE_STRONG
            hint = HINT_TIME_RANGE_STRONG

        handler = self.display_request(
            state,
            field="time_range",
            prompt_text=prompt_text,
            validation_hint=hint,
            validation_regex=r"^\\d{1,2}(:\\d{2})?\\s*-\\s*\\d{1,2}(:\\d{2})?$",
            turn_id=turn_id,
        )
        add_turn(state, role="assistant", text=prompt_text)
        return {
            "success": True,
            "result": prompt_text,
            "client_handler": handler,
        }

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
