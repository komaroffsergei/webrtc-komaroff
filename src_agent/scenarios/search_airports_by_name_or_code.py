from __future__ import annotations

import re
from typing import Any, Dict

from src_agent.scenarios.base import Scenario
from src_agent.tools.tools import get_artifact_by_key, search_airports_by_name_or_code, tool_context
from src_agent.utils.db import add_turn


class SearchAirportsByNameOrCodeScenario(Scenario):
    id = "search_airports_by_name_or_code"
    title = "Search airports by name or code"
    description = "Searches airports by name or code in airports.json."

    _quoted = re.compile(r"['\\\"]([^'\\\"]+)['\\\"]")

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

        pending = state.get("pending")
        if isinstance(pending, dict) and pending.get("scenario_id") == self.id and pending.get("field") == "query":
            query = self._extract_query(prompt, allow_sentence=True)
            if not query:
                return await self._ask_query(state, turn_id, llm_request=llm_request, user_text=prompt, invalid=True)
            state["pending"] = None
        else:
            query = self._extract_query(prompt, allow_sentence=True)
        if not query:
            return await self._ask_query(state, turn_id, llm_request=llm_request, user_text=prompt, invalid=False)

        with tool_context(state, self.id):
            _, res = search_airports_by_name_or_code(query=query)
            key = res.get("artifact_key") if isinstance(res, dict) else None
            if res.get("status") != "ok" or not isinstance(key, str):
                error_text = res.get("message") if isinstance(res, dict) else None
                error_text = str(error_text) if error_text else "Failed to search airports."
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
        summary = f"Found {count} airports for query '{query}'."
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

    async def _ask_query(self, state: Dict[str, Any], turn_id: str, *, llm_request, user_text: str, invalid: bool):
        meta = {
            "reason": "missing_required_parameter",
            "scenario_id": self.id,
            "missing": ["query"],
            "constraints": {"query": "airport name or airport code"},
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
            field="query",
            prompt_text=question,
            validation_hint="",
            validation_regex=None,
            meta=meta,
            turn_id=turn_id,
        )
        add_turn(state, role="assistant", text=question)
        return {"success": True, "result": question, "client_handler": handler}

    def _extract_query(self, prompt: str, *, allow_sentence: bool) -> str | None:
        match = self._quoted.search(prompt or "")
        if match:
            q = match.group(1).strip()
            return q if q else None

        cleaned = (prompt or "").strip()
        if not cleaned:
            return None

        lowered = cleaned.lower()
        for prefix in (
            "search",
            "find",
            "lookup",
            "найди",
            "найти",
            "поиск",
            "ищи",
            "ищите",
            "поищи",
        ):
            if lowered.startswith(prefix + " "):
                cleaned = cleaned[len(prefix) + 1 :].strip()
                break

        cleaned = re.sub(r"\b(airport|airports|aerodrome|aerodromes)\b", "", cleaned, flags=re.IGNORECASE).strip()
        cleaned = re.sub(r"\b(аэропорт|аэропорты|аэродром|аэродромы)\b", "", cleaned, flags=re.IGNORECASE).strip()
        cleaned = re.sub(r"^(by\s+(name|code))\b", "", cleaned, flags=re.IGNORECASE).strip()
        cleaned = re.sub(r"^(по\s+(названию|коду))\b", "", cleaned, flags=re.IGNORECASE).strip()
        cleaned = cleaned.strip(" :-,")
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        if not cleaned:
            return None

        if " " not in cleaned:
            return cleaned

        if not allow_sentence:
            return None

        tokens = cleaned.split(" ")
        if 1 <= len(tokens) <= 4 and all(tokens):
            return cleaned
        return None
