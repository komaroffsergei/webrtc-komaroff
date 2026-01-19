from __future__ import annotations

import re
from typing import Any, Dict

from src_agent.scenarios.base import Scenario
from src_agent.settings import (
    DEFAULT_NEAREST_AIRPORTS_RADIUS_KM,
    HINT_RADIUS,
    HINT_RADIUS_STRONG,
    NEAREST_AIRPORTS_SUMMARY_TEMPLATE,
    PROMPT_RADIUS,
    PROMPT_RADIUS_STRONG,
    SCENARIO_NEAREST_AIRPORTS_DESC,
    SCENARIO_NEAREST_AIRPORTS_TITLE,
)
from src_agent.tools.tools import ARTIFACTS, get_current_position, search_nearest_airports
from src_agent.utils.db import add_turn, save_artifact


class NearestAirportsScenario(Scenario):
    id = "nearest_airports"
    title = SCENARIO_NEAREST_AIRPORTS_TITLE
    description = SCENARIO_NEAREST_AIRPORTS_DESC
    input_hints = {"radius_km": "Радиус в километрах, целое число."}
    input_types = {"radius_km": "integer"}

    _radius_re = re.compile(r"(\d{1,4})\s*(?:км|km)?", re.IGNORECASE)

    async def handle(
        self,
        state: Dict[str, Any],
        *,
        prompt: str,
        turn_id: str,
        session_id: str,
        intent_id: str,
        db,
        llm_request=None,
    ):
        self.on_user_turn(state, prompt, turn_id)

        scenario_input = (state.get("scenario") or {}).get("input") or {}
        pending = (state.get("scenario") or {}).get("pending")
        if pending and pending.get("field") == "radius_km":
            radius = self._extract_radius(prompt)
            if radius is None:
                self._log(
                    state,
                    status="NEEDS_INPUT",
                    kind="INPUT_INVALID",
                    data={"field": "radius_km", "text": prompt},
                    turn_id=turn_id,
                )
                return self._ask_radius(state, turn_id, stronger=True)
            state["scenario"]["pending"] = None
            return await self._fetch_and_respond(
                state,
                radius_km=radius,
                turn_id=turn_id,
                session_id=session_id,
                intent_id=intent_id,
                db=db,
            )

        radius = scenario_input.get("radius_km")
        if isinstance(radius, str):
            radius = self._extract_radius(radius)
        if radius is None:
            radius = self._extract_radius(prompt)
        if radius is None:
            radius = DEFAULT_NEAREST_AIRPORTS_RADIUS_KM
        if radius is None:
            state["scenario"]["pending"] = {
                "field": "radius_km",
                "validation_regex": r"^\\d{1,4}$",
                "prompt": PROMPT_RADIUS,
                "hint": HINT_RADIUS,
                "status": "NEEDS_INPUT",
            }
            return self._ask_radius(state, turn_id, stronger=False)

        return await self._fetch_and_respond(
            state,
            radius_km=radius,
            turn_id=turn_id,
            session_id=session_id,
            intent_id=intent_id,
            db=db,
        )

    def _extract_radius(self, prompt: str) -> int | None:
        match = self._radius_re.search(prompt or "")
        if not match:
            return None
        value = int(match.group(1))
        return value if value > 0 else None

    def _ask_radius(self, state: Dict[str, Any], turn_id: str, *, stronger: bool):
        prompt_text = PROMPT_RADIUS
        hint = HINT_RADIUS
        if stronger:
            prompt_text = PROMPT_RADIUS_STRONG
            hint = HINT_RADIUS_STRONG

        handler = self.display_request(
            state,
            field="radius_km",
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

    async def _fetch_and_respond(
        self,
        state: Dict[str, Any],
        *,
        radius_km: int,
        turn_id: str,
        session_id: str,
        intent_id: str,
        db,
    ):
        self._log(
            state,
            status="RUNNING",
            kind="TOOL_CALLED",
            data={"tool": "get_current_position"},
            turn_id=turn_id,
        )
        try:
            _, pos_result = get_current_position()
        except Exception as exc:
            error_text = f"Failed to get current position: {exc}"
            handler = self.display_result(
                state,
                result_artifact_name="nearest_airports_error",
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

        if pos_result.get("status") != "ok":
            error_text = pos_result.get("message") or "Unable to get current position."
            handler = self.display_result(
                state,
                result_artifact_name="nearest_airports_error",
                summary_text=error_text,
                data={"error": pos_result},
                turn_id=turn_id,
            )
            add_turn(state, role="assistant", text=error_text)
            return {
                "success": True,
                "result": error_text,
                "client_handler": handler,
            }

        self._log(
            state,
            status="RUNNING",
            kind="TOOL_CALLED",
            data={"tool": "search_nearest_airports", "radius_km": radius_km},
            turn_id=turn_id,
        )
        try:
            _, airports_result = search_nearest_airports(radius_km=radius_km)
        except Exception as exc:
            error_text = f"Failed to search nearest airports: {exc}"
            handler = self.display_result(
                state,
                result_artifact_name="nearest_airports_error",
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

        if airports_result.get("status") != "ok":
            error_text = airports_result.get("message") or "Unable to search nearest airports."
            handler = self.display_result(
                state,
                result_artifact_name="nearest_airports_error",
                summary_text=error_text,
                data={"error": airports_result},
                turn_id=turn_id,
            )
            add_turn(state, role="assistant", text=error_text)
            return {
                "success": True,
                "result": error_text,
                "client_handler": handler,
            }

        airports = ARTIFACTS.get("selected_airports") or []
        summary_text = NEAREST_AIRPORTS_SUMMARY_TEMPLATE.format(radius_km=radius_km, count=len(airports))

        self._log(
            state,
            status="DONE",
            kind="TOOL_RESULT_STORED",
            data={"artifact": "selected_airports"},
            turn_id=turn_id,
        )

        handler = self.display_result(
            state,
            result_artifact_name="selected_airports",
            summary_text=summary_text,
            data={"airports": airports, "radius_km": radius_km},
            turn_id=turn_id,
        )

        await save_artifact(
            db,
            session_id=session_id,
            intent_id=intent_id,
            type="SCENARIO_ARTIFACT",
            name="selected_airports",
            data={"airports": airports, "radius_km": radius_km},
        )

        add_turn(state, role="assistant", text=summary_text)
        return {
            "success": True,
            "result": summary_text,
            "client_handler": handler,
        }

    def display_result(
        self,
        state: Dict[str, Any],
        *,
        result_artifact_name: str,
        summary_text: str,
        data: Dict[str, Any] | None,
        turn_id: str,
    ):
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
            "command": "SHOW_AIRPORTS",
            "artifacts": {
                "last": result_artifact_name,
                "all": [result_artifact_name],
                "payload": {result_artifact_name: artifact},
            },
        }
