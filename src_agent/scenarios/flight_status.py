from __future__ import annotations

from typing import Any, Dict

from src_agent.scenarios.base import Scenario
from src_agent.settings import (
    SCENARIO_FLIGHT_STATUS_DESC,
    SCENARIO_FLIGHT_STATUS_TITLE,
)
from src_agent.tools.tools import get_artifact, get_flight_status, tool_context
from src_agent.utils.db import add_turn


class FlightStatusScenario(Scenario):
    id = "flight_status"
    title = SCENARIO_FLIGHT_STATUS_TITLE
    description = SCENARIO_FLIGHT_STATUS_DESC
    llm_prompt = (
        "Ты извлекаешь один из следующих параметров:\n"
        "- flight_number: строка или null\n"
        "- surname: строка или null\n"
        "Правила:\n"
        "- Принимай любой пользовательский ввод (любая строка).\n"
        "- Самостоятельно определи, является ли ввод номером рейса или фамилией.\n"
        "- Если ты не можешь уверенно определить ни то ни другое, установи оба значения в null.\n"
        "- Никогда не выдумывай значения.\n"
    )

    input_hints = {
        "flight_number": "Номер рейса в любом формате или null, если отсутствует.",
        "surname": "Фамилия пассажира в любом формате или null, если отсутствует.",
    }

    input_types = {"flight_number": "string", "surname": "string"}

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

        scenario_input = (state.get("scenario") or {}).get("input")
        if not isinstance(scenario_input, dict):
            scenario_input = {}

        flight_number = scenario_input.get("flight_number")
        surname = scenario_input.get("surname")

        if isinstance(flight_number, str):
            return await self._fetch_and_respond(state, turn_id, flight_number=flight_number, surname=None)
        if isinstance(surname, str):
            return await self._fetch_and_respond(state, turn_id, flight_number=None, surname=surname)

        meta = {
            "reason": "missing_required_parameter",
            "scenario_id": self.id,
            "missing": ["flight_number", "surname"],
            "constraints": {
                "flight_number": "Example: SU100",
                "surname": "Example: Ivanov",
            },
        }

        try:
            question = await self.build_clarification_question(llm_request=llm_request, user_text=prompt, meta=meta)
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
            field="flight_query",
            prompt_text=question,
            validation_hint="",
            validation_regex=None,
            meta=meta,
            turn_id=turn_id,
        )
        add_turn(state, role="assistant", text=question)
        return {"success": True, "result": question, "client_handler": handler}

    async def _fetch_and_respond(
        self,
        state: Dict[str, Any],
        turn_id: str,
        *,
        flight_number: str | None,
        surname: str | None,
    ):
        self._log(
            state,
            status="RUNNING",
            kind="TOOL_CALLED",
            data={"tool": "get_flight_status"},
            turn_id=turn_id,
        )

        try:
            with tool_context(state, self.id):
                _, result = get_flight_status(flight_number=flight_number, surname=surname)
        except Exception as exc:
            error_text = f"Failed to fetch flight status: {exc}"
            handler = self.display_result(
                state,
                result_artifact_name="flight_status_error",
                summary_text=error_text,
                data={"error": str(exc)},
                turn_id=turn_id,
                command="SHOW_ERROR_MESSAGE",
            )
            add_turn(state, role="assistant", text=error_text)
            return {"success": True, "result": error_text, "client_handler": handler}

        if not isinstance(result, dict) or result.get("status") != "ok":
            error_text = "Unable to fetch flight status."
            handler = self.display_result(
                state,
                result_artifact_name="flight_status_error",
                summary_text=error_text,
                data={"error": result},
                turn_id=turn_id,
                command="SHOW_ERROR_MESSAGE",
            )
            add_turn(state, role="assistant", text=error_text)
            return {"success": True, "result": error_text, "client_handler": handler}

        with tool_context(state, self.id):
            data = get_artifact("flight_status")
        data_dict = data if isinstance(data, dict) else {}
        summary_text = self._format_summary(data_dict)
        handler = self.display_result(
            state,
            result_artifact_name="flight_status",
            summary_text=summary_text,
            data=data_dict,
            turn_id=turn_id,
        )
        add_turn(state, role="assistant", text=summary_text)
        return {"success": True, "result": summary_text, "client_handler": handler}

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
        surname = data.get("surname")

        parts = [
            f"Flight {flight_number} status: {status}.",
            f"Route: {from_airport} -> {to_airport}.",
            f"Departure: {departure}.",
            f"Arrival: {arrival}.",
        ]
        if surname:
            parts.append(f"Surname: {surname}.")
        if terminal or gate:
            parts.append(f"Terminal {terminal or '-'}, gate {gate or '-'}.")
        return " ".join(parts)
