from __future__ import annotations

import re
from typing import Any, Dict

from src_agent.scenarios.base import Scenario
from src_agent.settings import (
    HINT_FLIGHT_NUMBER,
    HINT_FLIGHT_NUMBER_STRONG,
    PROMPT_FLIGHT_NUMBER,
    PROMPT_FLIGHT_NUMBER_STRONG,
    SCENARIO_FLIGHT_STATUS_DESC,
    SCENARIO_FLIGHT_STATUS_TITLE,
)
from src_agent.tools.tools import get_artifact, get_flight_status, tool_context
from src_agent.utils.db import add_turn


class FlightStatusScenario(Scenario):
    id = "flight_status"
    title = SCENARIO_FLIGHT_STATUS_TITLE
    description = SCENARIO_FLIGHT_STATUS_DESC
    input_hints = {"flight_number": "Номер рейса, например SU100."}
    input_types = {"flight_number": "string"}

    _flight_re = re.compile(r"\b([A-Z]{1,3}\d{1,4})\b", re.IGNORECASE)

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
        if isinstance(pending, dict) and pending.get("scenario_id") == self.id and pending.get("field") == "flight_number":
            flight_number = self._extract_flight_number(prompt)
            if not flight_number:
                self._log(
                    state,
                    status="NEEDS_INPUT",
                    kind="INPUT_INVALID",
                    data={"field": "flight_number", "text": prompt},
                    turn_id=turn_id,
                )
                return self._ask_flight_number(state, turn_id, stronger=True)
            state["pending"] = None
            return await self._fetch_and_respond(
                state,
                flight_number=flight_number,
                turn_id=turn_id,
                session_id=session_id,
                db=db,
            )

        flight_number = scenario_input.get("flight_number")
        if isinstance(flight_number, str):
            flight_number = self._extract_flight_number(flight_number)
        flight_number = flight_number or self._extract_flight_number(prompt)
        if not flight_number:
            return self._ask_flight_number(state, turn_id, stronger=False)

        return await self._fetch_and_respond(
            state,
            flight_number=flight_number,
            turn_id=turn_id,
            session_id=session_id,
            db=db,
        )

    def _extract_flight_number(self, prompt: str) -> str | None:
        match = self._flight_re.search(prompt or "")
        if not match:
            return None
        return match.group(1).upper()

    def _ask_flight_number(self, state: Dict[str, Any], turn_id: str, *, stronger: bool):
        prompt_text = PROMPT_FLIGHT_NUMBER
        hint = HINT_FLIGHT_NUMBER
        if stronger:
            prompt_text = PROMPT_FLIGHT_NUMBER_STRONG
            hint = HINT_FLIGHT_NUMBER_STRONG

        handler = self.display_request(
            state,
            field="flight_number",
            prompt_text=prompt_text,
            validation_hint=hint,
            validation_regex=r"^[A-Z]{1,3}\\d{1,4}$",
            turn_id=turn_id,
        )
        add_turn(state, role="assistant", text=prompt_text)
        return {
            "success": True,
            "result": prompt_text,
            "client_handler": handler,
        }

    async def _fetch_and_respond(
        self,
        state: Dict[str, Any],
        *,
        flight_number: str,
        turn_id: str,
        session_id: str,
        db,
    ):
        self._log(
            state,
            status="RUNNING",
            kind="TOOL_CALLED",
            data={"tool": "get_flight_status", "flight_number": flight_number},
            turn_id=turn_id,
        )

        try:
            with tool_context(state, self.id):
                cont, result = get_flight_status(flight_number=flight_number)
        except Exception as exc:
            error_text = f"Failed to fetch flight status: {exc}"
            handler = self.display_result(
                state,
                result_artifact_name="flight_status_error",
                summary_text=error_text,
                data={"error": str(exc)},
                turn_id=turn_id,
            )
            add_turn(state, role="assistant", text=error_text)
            return {
                "success": True,
                "result": error_text,
                "client_handler": handler,
            }
        if result.get("status") != "ok":
            error_text = result.get("message") or "Unable to fetch flight status."
            handler = self.display_result(
                state,
                result_artifact_name="flight_status_error",
                summary_text=error_text,
                data={"error": result},
                turn_id=turn_id,
            )
            add_turn(state, role="assistant", text=error_text)
            return {
                "success": True,
                "result": error_text,
                "client_handler": handler,
            }

        with tool_context(state, self.id):
            data = get_artifact("flight_status") or {}
        summary_text = self._format_summary(data)

        self._log(
            state,
            status="DONE",
            kind="TOOL_RESULT_STORED",
            data={"artifact": "flight_status"},
            turn_id=turn_id,
        )

        handler = self.display_result(
            state,
            result_artifact_name="flight_status",
            summary_text=summary_text,
            data=data,
            turn_id=turn_id,
        )

        add_turn(state, role="assistant", text=summary_text)
        return {
            "success": True,
            "result": summary_text,
            "client_handler": handler,
        }

    def _format_summary(self, data: Dict[str, Any]) -> str:
        if not data:
            return "No flight status data is available."
        status = data.get("status", "UNKNOWN")
        flight_number = data.get("flight_number", "unknown flight")
        from_airport = data.get("from", "unknown")
        to_airport = data.get("to", "unknown")
        departure = data.get("departure_time", "unknown time")
        arrival = data.get("arrival_time", "unknown time")
        terminal = data.get("terminal")
        gate = data.get("gate")

        parts = [
            f"Flight {flight_number} status: {status}.",
            f"Route: {from_airport} -> {to_airport}.",
            f"Departure: {departure}.",
            f"Arrival: {arrival}.",
        ]
        if terminal or gate:
            parts.append(f"Terminal {terminal or '-'}, gate {gate or '-'}.")
        return " ".join(parts)
