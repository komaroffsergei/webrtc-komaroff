from __future__ import annotations

import json
from typing import Any, Dict

from src_agent.scenarios.base import Scenario
from src_agent.utils.db import add_turn


class AirportsClarifyScenario(Scenario):
    id = "airports_clarify"
    title = "Clarify airport request"
    description = "Clarifies an ambiguous airports request (not used for nearest/farthest by distance)."

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

        candidates = [
            "nearest_airports",
            "list_airports_all",
            "list_airports_open",
            "list_airports_closed",
            "search_airports_by_name_or_code",
        ]

        pending = state.get("pending")
        pending_active = (
            isinstance(pending, dict)
            and pending.get("scenario_id") == self.id
            and pending.get("field") == "airports_intent"
        )
        if pending_active:
            meta = pending.get("meta") if isinstance(pending.get("meta"), dict) else None
            if meta:
                meta_candidates = meta.get("candidates")
                if isinstance(meta_candidates, list) and all(isinstance(x, str) for x in meta_candidates):
                    candidates = meta_candidates

        choice = await self._select_candidate(llm_request, user_text=prompt, candidates=candidates)
        if isinstance(choice, str):
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

        return await self._ask_via_llm(state, turn_id, llm_request=llm_request, user_text=prompt, candidates=candidates)

    async def _ask_via_llm(
        self,
        state: Dict[str, Any],
        turn_id: str,
        *,
        llm_request,
        user_text: str,
        candidates: list[str],
    ):
        meta = {"reason": "airport_request_ambiguous", "candidates": candidates}
        try:
            question = await self.build_clarification_question(
                llm_request=llm_request,
                user_text=user_text,
                meta=meta,
            )
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
            field="airports_intent",
            prompt_text=question,
            validation_hint="",
            validation_regex=None,
            meta=meta,
            turn_id=turn_id,
        )
        add_turn(state, role="assistant", text=question)
        return {"success": True, "result": question, "client_handler": handler}

    async def _select_candidate(self, llm_request, *, user_text: str, candidates: list[str]) -> str | None:
        tool = {
            "type": "function",
            "function": {
                "name": "select_scenario",
                "description": "Select the most suitable scenario_id from the provided candidates.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "scenario_id": {"type": "string", "enum": candidates},
                        "reason": {"type": "string"},
                    },
                    "required": ["scenario_id"],
                },
            },
        }
        payload = {
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Choose the best scenario_id for the user's reply.\n"
                        "Rules:\n"
                        "- Use only the tool call.\n"
                        "- Do not ask follow-up questions.\n"
                    ),
                },
                {"role": "user", "content": json.dumps({"user_text": user_text}, ensure_ascii=False)},
            ],
            "tools": [tool],
            "think": False,
            "options": {"temperature": 0.0},
        }
        resp = await llm_request(payload)
        calls = (resp.get("message") or {}).get("tool_calls") or []
        for call in calls:
            fn = call.get("function") or {}
            if fn.get("name") != "select_scenario":
                continue
            args = fn.get("arguments") or {}
            scenario_id = args.get("scenario_id")
            return scenario_id if isinstance(scenario_id, str) else None
        return None
