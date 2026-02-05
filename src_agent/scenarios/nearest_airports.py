from __future__ import annotations

from typing import Any, Dict

from src_agent.scenarios.base import Scenario
from src_agent.settings import (
    NEAREST_AIRPORTS_SUMMARY_TEMPLATE,
    SCENARIO_NEAREST_AIRPORTS_DESC,
    SCENARIO_NEAREST_AIRPORTS_TITLE,
)
from src_agent.tools.tools import (
    build_route,
    find_airport_by_distance,
    get_artifact_by_key,
    get_current_position,
    search_nearest_airports,
    tool_context,
)
from src_agent.utils.db import add_turn


class NearestAirportsScenario(Scenario):
    """
    Сценарий поиска аэропортов “рядом со мной”.

    Параметры приходят из LLM params-extraction (state["scenario"]["input"]):
    - radius_km: радиус поиска (км) — обязателен для списка “в радиусе”
    - mode: "nearest"|"farthest" — режим выбора одного аэропорта по расстоянию
    - build_route: если true, дополнительно строим маршрут и отдаём UI события для карты
    """
    id = "nearest_airports"
    title = SCENARIO_NEAREST_AIRPORTS_TITLE
    description = SCENARIO_NEAREST_AIRPORTS_DESC
    llm_prompt = (
        "Извлеки параметры:\n"
        "- radius_km: целое число километров или null\n"
        "- mode: \"nearest\" | \"farthest\" | null\n"
        "- build_route: true или null\n"
        "Правила:\n"
        "- radius_km извлекай только если пользователь явно указал радиус в километрах.\n"
        "- mode=\"nearest\" извлекай только если пользователь просит ближайший/самый близкий аэропорт.\n"
        "- mode=\"farthest\" извлекай только если пользователь просит самый удалённый/самый дальний аэропорт.\n"
        "- build_route=true извлекай только если пользователь явно просит построить маршрут / проложить путь / как добраться.\n"
        "- Никогда не выдумывай значения.\n"
    )

    input_hints = {
        "radius_km": "Search radius in kilometers (integer) or null if missing.",
        "mode": "Either 'nearest' or 'farthest' when explicitly requested, otherwise null.",
        "build_route": "true if the user asks to build a route, otherwise null.",
    }
    input_types = {"radius_km": "integer", "mode": "string", "build_route": "boolean"}

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

        # `scenario_input` заполняется агентом перед вызовом handle(),
        # когда LLM вернул tool-call extract_params.
        scenario_input = (state.get("scenario") or {}).get("input")
        if not isinstance(scenario_input, dict):
            scenario_input = {}

        radius_km = scenario_input.get("radius_km")
        if not isinstance(radius_km, int) or radius_km <= 0:
            radius_km = None

        mode = scenario_input.get("mode")
        if mode not in ("nearest", "farthest"):
            mode = None

        build_route_requested = scenario_input.get("build_route")
        build_route_flag = build_route_requested is True

        if mode is not None:
            # Специальный режим: выбираем один аэропорт (ближайший/самый дальний),
            # радиус в этом случае не нужен.
            return await self._fetch_and_respond_by_distance(state, turn_id=turn_id, mode=mode, build_route=build_route_flag)

        pending = state.get("pending")
        if not build_route_flag and isinstance(pending, dict) and pending.get("scenario_id") == self.id:
            meta = pending.get("meta")
            if isinstance(meta, dict):
                requested = meta.get("requested")
                if isinstance(requested, dict) and requested.get("build_route") is True:
                    build_route_flag = True

        if radius_km is None:
            # Если радиус не указан явно — спрашиваем у пользователя уточнение и ставим pending.
            return await self._ask_radius(
                state,
                turn_id,
                llm_request=llm_request,
                user_text=prompt,
                build_route=build_route_flag,
            )

        return await self._fetch_and_respond(state, radius_km=radius_km, turn_id=turn_id, build_route=build_route_flag)

    async def _ask_radius(
        self,
        state: Dict[str, Any],
        turn_id: str,
        *,
        llm_request,
        user_text: str,
        build_route: bool,
    ):
        meta = {
            "reason": "missing_required_parameter",
            "scenario_id": self.id,
            "missing": ["radius_km"],
            "constraints": {"radius_km": "Example: 40 km"},
            "requested": {"build_route": build_route},
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
            field="radius_km",
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
        *,
        radius_km: int,
        turn_id: str,
        build_route: bool,
    ):
        self._log(
            state,
            status="RUNNING",
            kind="TOOL_CALLED",
            data={"tool": "get_current_position"},
            turn_id=turn_id,
        )
        try:
            with tool_context(state, self.id):
                _, pos_result = get_current_position()
                pos_key = pos_result.get("artifact_key") if isinstance(pos_result, dict) else None
                pos_artifact = get_artifact_by_key(pos_key) if isinstance(pos_key, str) else None
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

        if not isinstance(pos_result, dict) or pos_result.get("status") != "ok":
            error_text = (pos_result.get("message") if isinstance(pos_result, dict) else None) or "Unable to get current position."
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

        current_position = (pos_artifact.get("data") or {}).get("current_position") if isinstance(pos_artifact, dict) else None
        if not isinstance(current_position, dict):
            error_text = "Current position artifact is invalid."
            handler = self.display_result(
                state,
                result_artifact_name="nearest_airports_error",
                summary_text=error_text,
                data={"error": "invalid_current_position"},
                turn_id=turn_id,
                command="SHOW_ERROR_MESSAGE",
            )
            add_turn(state, role="assistant", text=error_text)
            return {"success": True, "result": error_text, "client_handler": handler}

        self._log(
            state,
            status="RUNNING",
            kind="TOOL_CALLED",
            data={"tool": "search_nearest_airports", "radius_km": radius_km},
            turn_id=turn_id,
        )
        try:
            with tool_context(state, self.id):
                _, airports_result = search_nearest_airports(radius_km=radius_km)
                airports_key = airports_result.get("artifact_key") if isinstance(airports_result, dict) else None
                airports_artifact = get_artifact_by_key(airports_key) if isinstance(airports_key, str) else None
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

        if not isinstance(airports_result, dict) or airports_result.get("status") != "ok":
            error_text = (airports_result.get("message") if isinstance(airports_result, dict) else None) or "Unable to search nearest airports."
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

        data = airports_artifact.get("data") if isinstance(airports_artifact, dict) else None
        airports = (data or {}).get("airports") if isinstance(data, dict) else []
        if not isinstance(airports, list):
            airports = []
        summary_text = NEAREST_AIRPORTS_SUMMARY_TEMPLATE.format(radius_km=radius_km, count=len(airports))

        handler = self.display_result(
            state,
            result_artifact_name=f"{self.id}.nearest_airports",
            summary_text=summary_text,
            data={"airports": airports, "radius_km": radius_km},
            turn_id=turn_id,
            command="SHOW_AIRPORTS",
        )

        client_events: list[dict] = []
        if build_route and airports:
            nearest = airports[0] if isinstance(airports[0], dict) else None
            if not isinstance(nearest, dict):
                error_text = "Nearest airport payload is invalid."
                handler = self.display_result(
                    state,
                    result_artifact_name="nearest_airports_error",
                    summary_text=error_text,
                    data={"error": "invalid_nearest_airport"},
                    turn_id=turn_id,
                    command="SHOW_ERROR_MESSAGE",
                )
                add_turn(state, role="assistant", text=error_text)
                return {"success": True, "result": error_text, "client_handler": handler}

            client_events = self._build_route_events(
                state,
                turn_id=turn_id,
                pos_key=pos_key,
                pos_artifact=pos_artifact,
                current_position=current_position,
                airport=nearest,
            )

        add_turn(state, role="assistant", text=summary_text)
        return {
            "success": True,
            "result": summary_text,
            "client_handler": handler,
            "client_events": client_events,
        }

    def _build_route_events(
        self,
        state: Dict[str, Any],
        *,
        turn_id: str,
        pos_key: str | None,
        pos_artifact: dict | None,
        current_position: dict,
        airport: dict,
    ) -> list[dict]:
        events: list[dict] = []
        if isinstance(pos_key, str) and isinstance(pos_artifact, dict):
            events.append({
                "command": "SET_POSITION",
                "artifacts": {"last": pos_key, "all": [pos_key], "payload": {pos_key: pos_artifact}},
            })

        start_lat = float(current_position.get("lat"))
        start_lon = float(current_position.get("lon"))
        end_lat = float(airport.get("lat"))
        end_lon = float(airport.get("lon"))
        with tool_context(state, self.id):
            _, route_result = build_route(start_lat=start_lat, start_lon=start_lon, end_lat=end_lat, end_lon=end_lon)
            route_key = route_result.get("artifact_key") if isinstance(route_result, dict) else None
            raw_route = get_artifact_by_key(route_key) if isinstance(route_key, str) else None

        geometry = (raw_route.get("data") or {}).get("geometry") if isinstance(raw_route, dict) else None
        distance = (raw_route.get("data") or {}).get("distance_km") if isinstance(raw_route, dict) else None
        route = {"from": {"lat": start_lat, "lon": start_lon}, "to": airport, "geometry": geometry, "distance_km": distance}

        artifact_key = f"{self.id}.result.route.{turn_id}"
        self._store_artifact(state, name=artifact_key, data={"data": {"route": route}})
        events.append({
            "command": "BUILD_ROUTE",
            "artifacts": {"last": artifact_key, "all": [artifact_key], "payload": {artifact_key: {"data": {"route": route}}}},
        })
        return events

    async def _fetch_and_respond_by_distance(
        self,
        state: Dict[str, Any],
        *,
        turn_id: str,
        mode: str,
        build_route: bool,
    ):
        try:
            with tool_context(state, self.id):
                _, pos_result = get_current_position()
                pos_key = pos_result.get("artifact_key") if isinstance(pos_result, dict) else None
                pos_artifact = get_artifact_by_key(pos_key) if isinstance(pos_key, str) else None

                _, sel_result = find_airport_by_distance(mode=mode)
                sel_key = sel_result.get("artifact_key") if isinstance(sel_result, dict) else None
                sel_artifact = get_artifact_by_key(sel_key) if isinstance(sel_key, str) else None
        except Exception as exc:
            error_text = f"Failed to select airport: {exc}"
            handler = self.display_result(
                state,
                result_artifact_name="nearest_airports_error",
                summary_text=error_text,
                data={"error": str(exc)},
                turn_id=turn_id,
                command="SHOW_ERROR_MESSAGE",
            )
            add_turn(state, role="assistant", text=error_text)
            return {"success": True, "result": error_text, "client_handler": handler}

        current_position = (pos_artifact.get("data") or {}).get("current_position") if isinstance(pos_artifact, dict) else None
        selected = (sel_artifact.get("data") or {}).get("airport") if isinstance(sel_artifact, dict) else None
        distance_km = (sel_artifact.get("data") or {}).get("distance_km") if isinstance(sel_artifact, dict) else None
        if not isinstance(current_position, dict) or not isinstance(selected, dict):
            raise RuntimeError("Scenario artifacts are invalid.")

        airport_with_distance = dict(selected)
        if isinstance(distance_km, (int, float)):
            airport_with_distance["distance_km"] = float(distance_km)

        handler = self.display_result(
            state,
            result_artifact_name=f"{self.id}.nearest_airports",
            summary_text="",
            data={"airports": [airport_with_distance]},
            turn_id=turn_id,
            command="SHOW_AIRPORTS",
        )

        client_events = (
            self._build_route_events(
                state,
                turn_id=turn_id,
                pos_key=pos_key if isinstance(pos_key, str) else None,
                pos_artifact=pos_artifact if isinstance(pos_artifact, dict) else None,
                current_position=current_position,
                airport=selected,
            )
            if build_route
            else []
        )

        add_turn(state, role="assistant", text="")
        return {"success": True, "result": "", "client_handler": handler, "client_events": client_events}
