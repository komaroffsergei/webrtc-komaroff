from __future__ import annotations

import re
from typing import Any, Dict, Optional, Tuple

from src_agent.scenarios.base import Scenario
from src_agent.utils.db import add_turn


class FlightsBetweenTimesScenario(Scenario):
    id = "flights_between_times"

    _time_re = re.compile(r"\b([01]?\d|2[0-3])(?::([0-5]\d))?\b")

    def matches(self, prompt: str) -> bool:
        lowered = prompt.lower()
        if "between" in lowered or "между" in lowered:
            return True
        start_time, end_time = self._extract_time_range(prompt)
        if start_time and end_time and ("flight" in lowered or "рейс" in lowered):
            return True
        return False

    async def handle(
        self,
        state: Dict[str, Any],
        *,
        prompt: str,
        turn_id: str,
        session_id: str,
        intent_id: str,
        db,
    ):
        self.on_user_turn(state, prompt, turn_id)

        pending = (state.get("scenario") or {}).get("pending")
        if pending and pending.get("field") == "time_range":
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
            state["scenario"]["pending"] = None
            return self._respond_placeholder(state, turn_id, start_time, end_time)

        start_time, end_time = self._extract_time_range(prompt)
        if not start_time or not end_time:
            state["scenario"]["pending"] = {
                "field": "time_range",
                "validation_regex": r"^\\d{1,2}(:\\d{2})?\\s*-\\s*\\d{1,2}(:\\d{2})?$",
                "prompt": "Please provide a time range (e.g., 12:00-16:00).",
                "hint": "Use HH:MM-HH:MM or HH-HH format.",
                "status": "NEEDS_INPUT",
            }
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
        prompt_text = "Please provide a time range (e.g., 12:00-16:00)."
        hint = "Use HH:MM-HH:MM or HH-HH format."
        if stronger:
            prompt_text = "Please provide a valid time range, e.g., 12:00-16:00."
            hint = "Provide two times, like 12:00-16:00."

        handler = self.display_request(
            state,
            field="time_range",
            prompt_text=prompt_text,
            validation_hint=hint,
            turn_id=turn_id,
        )
        add_turn(state, role="assistant", text=prompt_text)
        return {
            "success": True,
            "result": prompt_text,
            "client_handler": handler,
        }

    def _respond_placeholder(self, state: Dict[str, Any], turn_id: str, start: str, end: str):
        summary = (
            "Flight search between times is not available yet. "
            f"Requested window: {start}-{end}."
        )
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
