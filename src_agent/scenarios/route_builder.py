from __future__ import annotations

import json
import re
from typing import Any, Dict, Optional

from src_agent.scenarios.base import Scenario
from src_agent.tools.tools import (
    build_route,
    get_artifact_by_key,
    get_current_position,
    list_airports,
    resolve_airport,
    tool_context,
)
from src_agent.utils.db import add_turn


class RouteBuilderScenario(Scenario):
    id = "route_builder"
    title = "Route builder"
    description = "Builds a great-circle route between airports or from current position to an airport."

    _between_re = re.compile(r"\b(между)\b", re.IGNORECASE)
    _to_re = re.compile(r"\b(до)\b", re.IGNORECASE)
    _from_re = re.compile(r"\b(от|из)\b", re.IGNORECASE)

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
            if isinstance(state.get("scenario"), dict):
                state["scenario"]["input"] = scenario_input

        mode = self._detect_mode(prompt) or scenario_input.get("mode")
        if mode not in ("TO", "BETWEEN"):
            meta = {"reason": "missing_mode", "candidates": ["TO", "BETWEEN"]}
            return await self._ask(state, turn_id, llm_request=llm_request, user_text=prompt, field="mode", meta=meta)
        scenario_input["mode"] = mode

        pending = state.get("pending")
        if isinstance(pending, dict) and pending.get("scenario_id") == self.id:
            field = pending.get("field")
            meta = pending.get("meta") if isinstance(pending.get("meta"), dict) else {}
            if field in ("from_airport", "to_airport", "route_endpoints"):
                return await self._continue_with_user_input(
                    state,
                    turn_id,
                    llm_request=llm_request,
                    user_text=prompt,
                    field=str(field),
                    meta=meta,
                    session_id=session_id,
                    db=db,
                    request_id=request_id,
                )

        from_text, to_text = self._extract_endpoints(prompt, mode=mode)

        from_airport = scenario_input.get("from_airport") if isinstance(scenario_input.get("from_airport"), dict) else None
        to_airport = scenario_input.get("to_airport") if isinstance(scenario_input.get("to_airport"), dict) else None

        if mode == "BETWEEN":
            if from_airport is None and from_text:
                from_airport = await self._resolve_or_ask(
                    state, turn_id, llm_request=llm_request, field="from_airport", user_text=from_text
                )
                if from_airport is None:
                    return None
                scenario_input["from_airport"] = from_airport
            if to_airport is None and to_text:
                to_airport = await self._resolve_or_ask(
                    state, turn_id, llm_request=llm_request, field="to_airport", user_text=to_text
                )
                if to_airport is None:
                    return None
                scenario_input["to_airport"] = to_airport

            if from_airport is None or to_airport is None:
                missing = []
                if from_airport is None:
                    missing.append("from_airport")
                if to_airport is None:
                    missing.append("to_airport")
                meta = {"reason": "missing_route_endpoints", "mode": mode, "missing": missing}
                return await self._ask(
                    state,
                    turn_id,
                    llm_request=llm_request,
                    user_text=prompt,
                    field="route_endpoints",
                    meta=meta,
                )

            return await self._build_and_respond_between(
                state,
                turn_id,
                from_airport=from_airport,
                to_airport=to_airport,
            )

        if to_airport is None and to_text:
            to_airport = await self._resolve_or_ask(
                state, turn_id, llm_request=llm_request, field="to_airport", user_text=to_text
            )
            if to_airport is None:
                return None
            scenario_input["to_airport"] = to_airport

        if to_airport is None:
            meta = {"reason": "missing_destination_airport", "mode": mode, "missing": ["to_airport"]}
            return await self._ask(
                state,
                turn_id,
                llm_request=llm_request,
                user_text=prompt,
                field="to_airport",
                meta=meta,
            )

        return await self._build_and_respond_to(
            state,
            turn_id,
            to_airport=to_airport,
        )

    def _detect_mode(self, text: str) -> str | None:
        t = text or ""
        if self._between_re.search(t) or (self._from_re.search(t) and self._to_re.search(t)):
            return "BETWEEN"
        if self._to_re.search(t) and not self._between_re.search(t):
            return "TO"
        return None

    def _extract_endpoints(self, text: str, *, mode: str) -> tuple[str | None, str | None]:
        t = (text or "").strip()
        if not t:
            return None, None

        from_text = None
        to_text = None

        if mode == "BETWEEN":
            m = re.search(r"(?:^|\s)(?:от|из)\s+(.+?)(?:\s+(?:до|в|к)\s+|$)", t, flags=re.IGNORECASE)
            if m:
                from_text = m.group(1).strip()
            m = re.search(r"(?:^|\s)(?:до|в|к)\s+(.+)$", t, flags=re.IGNORECASE)
            if m:
                to_text = m.group(1).strip()
        else:
            m = re.search(r"(?:^|\s)(?:до|в|к)\s+(.+)$", t, flags=re.IGNORECASE)
            if m:
                to_text = m.group(1).strip()
        return from_text or None, to_text or None

    async def _continue_with_user_input(
        self,
        state: Dict[str, Any],
        turn_id: str,
        *,
        llm_request,
        user_text: str,
        field: str,
        meta: Dict[str, Any],
        session_id: str,
        db,
        request_id: str,
    ):
        scenario_input = (state.get("scenario") or {}).get("input") or {}

        if field == "route_endpoints":
            mode = scenario_input.get("mode")
            from_text, to_text = self._extract_endpoints(user_text, mode=mode)
            if not from_text and not to_text:
                meta = {"reason": "missing_route_endpoints", "mode": mode, "missing": ["from_airport", "to_airport"]}
                return await self._ask(state, turn_id, llm_request=llm_request, user_text=user_text, field=field, meta=meta)

            if from_text and not scenario_input.get("from_airport"):
                a = await self._resolve_or_ask(state, turn_id, llm_request=llm_request, field="from_airport", user_text=from_text)
                if a is None:
                    return None
                scenario_input["from_airport"] = a
            if to_text and not scenario_input.get("to_airport"):
                a = await self._resolve_or_ask(state, turn_id, llm_request=llm_request, field="to_airport", user_text=to_text)
                if a is None:
                    return None
                scenario_input["to_airport"] = a

            state["pending"] = None
            return await self.handle(
                state,
                prompt=user_text,
                turn_id=turn_id,
                session_id=session_id,
                db=db,
                llm_request=llm_request,
                request_id=request_id,
            )

        if field in ("from_airport", "to_airport"):
            a = await self._resolve_or_ask(state, turn_id, llm_request=llm_request, field=field, user_text=user_text, meta=meta)
            if a is None:
                return None
            scenario_input[field] = a
            state["pending"] = None
            return await self.handle(
                state,
                prompt=user_text,
                turn_id=turn_id,
                session_id=session_id,
                db=db,
                llm_request=llm_request,
                request_id=request_id,
            )

        return None

    async def _resolve_or_ask(
        self,
        state: Dict[str, Any],
        turn_id: str,
        *,
        llm_request,
        field: str,
        user_text: str,
        meta: Dict[str, Any] | None = None,
    ) -> dict | None:
        options = (meta or {}).get("options") if isinstance((meta or {}).get("options"), list) else None
        if options:
            picked = await self._pick_from_options(llm_request, user_text=user_text, options=options)
            if picked:
                return picked

        with tool_context(state, self.id):
            _, res = resolve_airport(user_text=user_text)

        status = res.get("status") if isinstance(res, dict) else None
        if status == "ok":
            airport = res.get("airport")
            return airport if isinstance(airport, dict) else None
        if status == "ambiguous":
            opts = res.get("options") if isinstance(res.get("options"), list) else []
            meta = {
                "reason": "airport_ambiguous",
                "field": field,
                "options": opts,
            }
            await self._ask(state, turn_id, llm_request=llm_request, user_text=user_text, field=field, meta=meta)
            return None
        if status == "not_found":
            meta = {
                "reason": "airport_not_found",
                "field": field,
                "missing": [field],
            }
            await self._ask(state, turn_id, llm_request=llm_request, user_text=user_text, field=field, meta=meta)
            return None

        error_text = f"Airport resolution failed: {res}"
        handler = self.display_result(
            state,
            result_artifact_name="error",
            summary_text=error_text,
            data={"error": res},
            turn_id=turn_id,
            command="SHOW_ERROR_MESSAGE",
        )
        add_turn(state, role="assistant", text=error_text)
        return None if handler else None

    async def _ask(self, state: Dict[str, Any], turn_id: str, *, llm_request, user_text: str, field: str, meta: Dict[str, Any]):
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
            field=field,
            prompt_text=question,
            validation_hint="",
            validation_regex=None,
            meta=meta,
            turn_id=turn_id,
        )
        add_turn(state, role="assistant", text=question)
        return {"success": True, "result": question, "client_handler": handler}

    async def _pick_from_options(self, llm_request, *, user_text: str, options: list[dict]) -> dict | None:
        enum_values: list[str] = []
        by_key: dict[str, dict] = {}
        for o in options:
            if not isinstance(o, dict):
                continue
            key = str(o.get("code") or o.get("id") or "")
            if not key:
                continue
            if key not in by_key:
                by_key[key] = o
                enum_values.append(key)
        if not enum_values:
            return None

        tool = {
            "type": "function",
            "function": {
                "name": "select_option",
                "description": "Select the best matching airport option.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "key": {"type": "string", "enum": enum_values},
                    },
                    "required": ["key"],
                },
            },
        }
        payload = {
            "messages": [
                {"role": "system", "content": "Use the tool to select the best matching option."},
                {"role": "user", "content": json.dumps({"user_text": user_text, "options": options}, ensure_ascii=False)},
            ],
            "tools": [tool],
            "think": False,
            "options": {"temperature": 0.0},
        }
        resp = await llm_request(payload)
        calls = (resp.get("message") or {}).get("tool_calls") or []
        for call in calls:
            fn = call.get("function") or {}
            if fn.get("name") != "select_option":
                continue
            args = fn.get("arguments") or {}
            key = args.get("key")
            if isinstance(key, str) and key in by_key:
                return by_key[key]
        return None

    async def _ensure_map_prereqs(self, state: Dict[str, Any], turn_id: str) -> tuple[list[dict], dict | None]:
        client_events: list[dict] = []
        current_position: dict | None = None

        with tool_context(state, self.id):
            _, res = list_airports()
            key = res.get("artifact_key") if isinstance(res, dict) else None
            if isinstance(key, str):
                artifact = get_artifact_by_key(key)
                client_events.append({
                    "command": "SET_AIRPORTS",
                    "artifacts": {"last": key, "all": [key], "payload": {key: artifact}},
                })

        with tool_context(state, self.id):
            _, res = get_current_position()
            key = res.get("artifact_key") if isinstance(res, dict) else None
            if isinstance(key, str):
                artifact = get_artifact_by_key(key)
                client_events.append({
                    "command": "SET_POSITION",
                    "artifacts": {"last": key, "all": [key], "payload": {key: artifact}},
                })
                pos = (artifact.get("data") or {}).get("current_position") if isinstance(artifact, dict) else None
                current_position = pos if isinstance(pos, dict) else None

        return client_events, current_position

    async def _build_and_respond_between(
        self,
        state: Dict[str, Any],
        turn_id: str,
        *,
        from_airport: dict,
        to_airport: dict,
    ):
        client_events, _ = await self._ensure_map_prereqs(state, turn_id)

        start_lat = float(from_airport.get("lat"))
        start_lon = float(from_airport.get("lon"))
        end_lat = float(to_airport.get("lat"))
        end_lon = float(to_airport.get("lon"))
        with tool_context(state, self.id):
            _, res = build_route(start_lat=start_lat, start_lon=start_lon, end_lat=end_lat, end_lon=end_lon)
            key = res.get("artifact_key") if isinstance(res, dict) else None
            raw = get_artifact_by_key(key) if isinstance(key, str) else None

        geometry = (raw.get("data") or {}).get("geometry") if isinstance(raw, dict) else None
        distance = (raw.get("data") or {}).get("distance_km") if isinstance(raw, dict) else None
        route = {"from": from_airport, "to": to_airport, "geometry": geometry, "distance_km": distance}

        artifact_key = f"{self.id}.result.route.{turn_id}"
        self._store_artifact(state, name=artifact_key, data={"data": {"route": route}})
        handler = {"command": "BUILD_ROUTE", "artifacts": {"last": artifact_key, "all": [artifact_key], "payload": {artifact_key: {"data": {"route": route}}}}}

        result_text = f"Маршрут построен: {float(distance):.1f} км" if isinstance(distance, (int, float)) else "Маршрут построен."
        add_turn(state, role="assistant", text=result_text)
        return {"success": True, "result": result_text, "client_handler": handler, "client_events": client_events}

    async def _build_and_respond_to(
        self,
        state: Dict[str, Any],
        turn_id: str,
        *,
        to_airport: dict,
    ):
        client_events, current_position = await self._ensure_map_prereqs(state, turn_id)
        if not current_position:
            error_text = "Failed to get current position."
            handler = self.display_result(
                state,
                result_artifact_name="error",
                summary_text=error_text,
                data={"error": "no_current_position"},
                turn_id=turn_id,
                command="SHOW_ERROR_MESSAGE",
            )
            add_turn(state, role="assistant", text=error_text)
            return {"success": True, "result": error_text, "client_handler": handler}

        start_lat = float(current_position.get("lat"))
        start_lon = float(current_position.get("lon"))
        end_lat = float(to_airport.get("lat"))
        end_lon = float(to_airport.get("lon"))

        with tool_context(state, self.id):
            _, res = build_route(start_lat=start_lat, start_lon=start_lon, end_lat=end_lat, end_lon=end_lon)
            key = res.get("artifact_key") if isinstance(res, dict) else None
            raw = get_artifact_by_key(key) if isinstance(key, str) else None

        geometry = (raw.get("data") or {}).get("geometry") if isinstance(raw, dict) else None
        distance = (raw.get("data") or {}).get("distance_km") if isinstance(raw, dict) else None
        route = {"from": {"lat": start_lat, "lon": start_lon}, "to": to_airport, "geometry": geometry, "distance_km": distance}

        artifact_key = f"{self.id}.result.route.{turn_id}"
        self._store_artifact(state, name=artifact_key, data={"data": {"route": route}})
        handler = {"command": "BUILD_ROUTE", "artifacts": {"last": artifact_key, "all": [artifact_key], "payload": {artifact_key: {"data": {"route": route}}}}}

        result_text = f"Маршрут построен: {float(distance):.1f} км" if isinstance(distance, (int, float)) else "Маршрут построен."
        add_turn(state, role="assistant", text=result_text)
        return {"success": True, "result": result_text, "client_handler": handler, "client_events": client_events}
