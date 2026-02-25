from __future__ import annotations

import asyncio
import json
import logging
import re
import signal
from typing import Any, TypedDict
from uuid import uuid4

import nats
from langgraph.graph import END, StateGraph
from nats.aio.client import Client as NATS
from nats.aio.msg import Msg

from src_shared.contracts import (
    ErrorInfo,
    LlmRequest,
    LlmResponse,
    N8nRunRequest,
    N8nRunResponse,
    N8nRuntimeState,
    ServiceHealthRequest,
    ServiceHealthResponse,
    ToolCallRequest,
    ToolCallResponse,
    now_ts_ms,
)

logger = logging.getLogger("src_langgraph")

SC_ECHO = "echo@2.0.0"
SC_WHERE_MY_FLIGHT = "where_my_flight@2.0.0"
SC_FIND_NEAREST_AIRPORT = "find_nearest_airport@2.0.0"
SC_FREE_SPEECH = "free_speech@2.0.0"

ROUTER_TASK_RU = (
    "Определи, какой сценарий лучше всего подходит для запроса пользователя. "
    "Выбирай только один сценарий из списка."
)
ROUTER_SCENARIOS = [
    {
        "id": SC_WHERE_MY_FLIGHT,
        "description": "Найти статус рейса по номеру рейса или фамилии пассажира, при нехватке данных запросить уточнение",
    },
    {
        "id": SC_FIND_NEAREST_AIRPORT,
        "description": "Найти ближайший аэропорт и построить маршрут до него",
    },
    {
        "id": SC_FREE_SPEECH,
        "description": "Свободный разговор: общение с пользователем без сценария и инструментов",
    },
]

FLIGHT_TOOL_PARAMS_TASK_RU = (
    "Определи параметры для поиска статуса рейса.\n"
    "Если параметров не хватает, верни missing и задай пользователю уточняющий вопрос на русском.\n"
    "Если параметр распознан как номер рейса — нормализуй его (удали пробелы внутри номера рейса)."
)
FLIGHT_FINAL_TASK_RU = "Сформируй понятный ответ пользователю по результату поиска рейса.\nПиши по-русски."
FLIGHT_SCENARIO_CONTEXT_RU = (
    "Пользователь хочет узнать статус рейса.\n"
    "Ответ должен быть кратким, понятным и на русском языке."
)
FLIGHT_TOOL_SCHEMA = {
    "parameters": {
        "flight_number": {"type": "string", "description": "Номер рейса, например SU123"},
        "last_name": {"type": "string", "description": "Фамилия пассажира"},
    }
}

AIRPORT_SEARCH_PARAMS_TASK_RU = (
    "Подготовь параметры для поиска ближайших аэропортов.\n"
    "Если город не указан явно, используй данные о текущей позиции из tool_results.\n"
    "Радиус поиска можно выбрать по умолчанию, если пользователь не указал."
)
AIRPORT_SEARCH_TOOL_SCHEMA = {
    "parameters": {
        "city": {"type": "string", "description": "Город для поиска ближайших аэропортов"},
        "radius_km": {"type": "number", "description": "Радиус поиска в километрах", "default": 50},
    }
}
AIRPORT_ROUTE_PARAMS_TASK_RU = (
    "Подготовь параметры для построения маршрута до выбранного аэропорта.\n"
    "Используй текущую позицию пользователя и координаты первого найденного аэропорта из tool_results."
)
AIRPORT_ROUTE_TOOL_SCHEMA = {
    "parameters": {
        "from_lat": {"type": "number", "description": "Широта точки отправления"},
        "from_lon": {"type": "number", "description": "Долгота точки отправления"},
        "to_lat": {"type": "number", "description": "Широта точки назначения"},
        "to_lon": {"type": "number", "description": "Долгота точки назначения"},
    }
}
AIRPORT_FINAL_TASK_RU = (
    "Сформируй финальный ответ пользователю по найденному ближайшему аэропорту и маршруту.\n"
    "Пиши по-русски.\n"
    "Если данных мало, честно сообщи об этом."
)
AIRPORT_SCENARIO_CONTEXT_RU = (
    "Пользователь хочет найти ближайший аэропорт и построить маршрут до него.\n"
    "Ответ должен учитывать найденный аэропорт и построенный маршрут."
)

FREE_SPEECH_FINAL_TASK_RU = (
    "Побеседуй с пользователем в свободной форме.\n"
    "Отвечай кратко, по-русски, дружелюбно и по делу.\n"
    "Если вопрос непонятен, задай уточняющий вопрос."
)
FREE_SPEECH_SCENARIO_CONTEXT_RU = (
    "Свободный диалог без сценария.\n"
    "Инструменты не используются.\n"
    "Цель — помочь пользователю и поддерживать разговор."
)

FLIGHT_NOT_FOUND_MESSAGE_RU = (
    "Статус рейса не найден.\nПожалуйста, проверьте номер рейса или попробуйте поиск по фамилии пассажира."
)
FLIGHT_ASK_INPUT_DEFAULT_RU = "Укажите номер рейса (например, SU123) или фамилию пассажира."


class OrchestratorState(TypedDict, total=False):
    req: N8nRunRequest
    selected_workflow_id: str
    routing: dict[str, Any]
    response: N8nRunResponse


class LangGraphWorkflowService:
    def __init__(
        self,
        *,
        nats_url: str,
        run_subject: str,
        health_subject: str,
        llm_subject_prefix: str,
        tools_subject_prefix: str,
        user_id: str,
        request_timeout_s: float = 120.0,
        max_concurrency: int = 8,
    ) -> None:
        self.nats_url = nats_url
        self.run_subject = run_subject
        self.health_subject = health_subject
        self.llm_subject_prefix = llm_subject_prefix
        self.tools_subject_prefix = tools_subject_prefix
        self.user_id = user_id
        self.request_timeout_s = float(request_timeout_s)
        self._stop = asyncio.Event()
        self._tasks: set[asyncio.Task[Any]] = set()
        self._semaphore = asyncio.Semaphore(max(1, int(max_concurrency)))
        self._nc: NATS | None = None
        self._graph = self._build_graph()

    def _build_graph(self):
        builder = StateGraph(OrchestratorState)
        builder.add_node("dispatch", self._node_dispatch)
        builder.add_node("scenario_echo", self._node_scenario_echo)
        builder.add_node("scenario_where_my_flight", self._node_scenario_where_my_flight)
        builder.add_node("scenario_find_nearest_airport", self._node_scenario_find_nearest_airport)
        builder.add_node("scenario_free_speech", self._node_scenario_free_speech)

        builder.set_entry_point("dispatch")
        builder.add_conditional_edges(
            "dispatch",
            self._route_after_dispatch,
            {
                SC_ECHO: "scenario_echo",
                SC_WHERE_MY_FLIGHT: "scenario_where_my_flight",
                SC_FIND_NEAREST_AIRPORT: "scenario_find_nearest_airport",
                SC_FREE_SPEECH: "scenario_free_speech",
            },
        )
        builder.add_edge("scenario_echo", END)
        builder.add_edge("scenario_where_my_flight", END)
        builder.add_edge("scenario_find_nearest_airport", END)
        builder.add_edge("scenario_free_speech", END)
        return builder.compile()

    async def run(self) -> None:
        nc = await nats.connect(
            servers=[self.nats_url],
            name="src_langgraph",
            max_reconnect_attempts=-1,
            reconnect_time_wait=2,
            ping_interval=10,
        )
        self._nc = nc

        await nc.subscribe(self.run_subject, queue="src_langgraph.run.q", cb=self._handle_run)
        await nc.subscribe(self.health_subject, queue="src_langgraph.health.q", cb=self._handle_health)
        logger.info("Subscribed to %s and %s", self.run_subject, self.health_subject)

        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, lambda s=sig: asyncio.create_task(self.shutdown(s)))
            except NotImplementedError:
                pass

        await self._stop.wait()
        for task in list(self._tasks):
            task.cancel()
        await nc.drain()
        await nc.close()
        self._nc = None

    async def shutdown(self, signal_obj=None) -> None:
        logger.info("Shutdown requested: %s", getattr(signal_obj, "name", signal_obj))
        self._stop.set()

    async def _handle_run(self, msg: Msg) -> None:
        task = asyncio.create_task(self._process_run_message(msg))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _process_run_message(self, msg: Msg) -> None:
        async with self._semaphore:
            try:
                raw = json.loads(msg.data.decode("utf-8"))
                req = N8nRunRequest.model_validate(raw)
            except Exception as exc:
                logger.exception("Invalid run payload")
                resp = N8nRunResponse(
                    trace_id=uuid4(),
                    correlation_id=None,
                    request_id=uuid4(),
                    session_id=None,
                    ts_ms=now_ts_ms(),
                    status="FAILED",
                    result="",
                    errors=[ErrorInfo(code="invalid_request", message=str(exc))],
                )
                await self._safe_respond(msg, resp.model_dump_json().encode("utf-8"))
                return

            if req.session_id is None:
                resp = self._failed_response(
                    req,
                    code="missing_session_id",
                    message="session_id is required",
                    next_runtime=req.runtime,
                )
                await self._safe_respond(msg, resp.model_dump_json().encode("utf-8"))
                return

            try:
                state = await self._graph.ainvoke({"req": req})
                resp = state.get("response")
                if not isinstance(resp, N8nRunResponse):
                    raise RuntimeError("LangGraph workflow did not produce N8nRunResponse")
            except Exception as exc:
                logger.exception("Workflow execution failed")
                resp = self._failed_response(
                    req,
                    code="workflow_failed",
                    message=str(exc),
                    next_runtime=req.runtime,
                )

            await self._safe_respond(msg, resp.model_dump_json().encode("utf-8"))

    async def _handle_health(self, msg: Msg) -> None:
        try:
            raw = json.loads(msg.data.decode("utf-8"))
            req = ServiceHealthRequest.model_validate(raw)
            resp = ServiceHealthResponse(
                trace_id=req.trace_id,
                correlation_id=req.correlation_id,
                request_id=req.request_id,
                session_id=req.session_id,
                ts_ms=now_ts_ms(),
                ok=self._nc is not None,
                status="healthy" if self._nc is not None else "unhealthy",
                details={"service": "src_langgraph", "run_subject": self.run_subject},
            )
        except Exception as exc:
            resp = ServiceHealthResponse(
                trace_id=uuid4(),
                correlation_id=None,
                request_id=uuid4(),
                session_id=None,
                ts_ms=now_ts_ms(),
                ok=False,
                status="unhealthy",
                details={"service": "src_langgraph"},
                error=ErrorInfo(code="health_failed", message=str(exc)),
            )
        await self._safe_respond(msg, resp.model_dump_json().encode("utf-8"))

    async def _safe_respond(self, msg: Msg, payload: bytes) -> None:
        if not msg.reply:
            return
        try:
            await msg.respond(payload)
        except Exception:
            logger.exception("Failed to respond on NATS")

    def _route_after_dispatch(self, state: OrchestratorState) -> str:
        workflow_id = str(state.get("selected_workflow_id") or "").strip()
        if workflow_id in {SC_ECHO, SC_WHERE_MY_FLIGHT, SC_FIND_NEAREST_AIRPORT, SC_FREE_SPEECH}:
            return workflow_id
        return SC_FREE_SPEECH

    async def _node_dispatch(self, state: OrchestratorState) -> dict[str, Any]:
        req = state["req"]
        pending = req.runtime.pending if isinstance(req.runtime.pending, dict) else None
        active = (req.runtime.active_workflow_id or "").strip()

        if active == SC_WHERE_MY_FLIGHT and pending:
            return {"selected_workflow_id": SC_WHERE_MY_FLIGHT}

        if self._is_explicit_echo(req.text):
            return {"selected_workflow_id": SC_ECHO}

        route_resp = await self._call_llm(
            parent=req,
            mode="routing_decision",
            input_data={
                "task": ROUTER_TASK_RU,
                "text": req.text,
                "available_scenarios": ROUTER_SCENARIOS,
            },
            constraints={"temperature": 0},
        )

        workflow_id = SC_FREE_SPEECH
        routing_data: dict[str, Any] = {}
        if route_resp.ok and isinstance(route_resp.data, dict):
            routing_data = dict(route_resp.data)
            candidate = str(route_resp.data.get("workflow_id") or "").strip()
            if candidate == SC_WHERE_MY_FLIGHT:
                workflow_id = SC_WHERE_MY_FLIGHT
            elif candidate == SC_FIND_NEAREST_AIRPORT:
                workflow_id = SC_FIND_NEAREST_AIRPORT
            elif candidate == SC_ECHO:
                workflow_id = SC_ECHO if self._is_explicit_echo(req.text) else SC_FREE_SPEECH
            elif candidate == SC_FREE_SPEECH:
                workflow_id = SC_FREE_SPEECH
            else:
                workflow_id = SC_FREE_SPEECH

        return {"selected_workflow_id": workflow_id, "routing": routing_data}

    async def _node_scenario_echo(self, state: OrchestratorState) -> dict[str, Any]:
        req = state["req"]
        text = self._echo_payload_text(req.text)
        if not text.strip():
            text = req.text.strip()
        resp = self._done_message_response(req, text or "Пустое сообщение.")
        return {"response": resp}

    async def _node_scenario_free_speech(self, state: OrchestratorState) -> dict[str, Any]:
        req = state["req"]
        llm_resp = await self._call_llm(
            parent=req,
            mode="final_response",
            input_data={
                "task": FREE_SPEECH_FINAL_TASK_RU,
                "user_message": req.text,
                "tool_results": [],
                "scenario_context": FREE_SPEECH_SCENARIO_CONTEXT_RU,
            },
            constraints={"temperature": 0.4},
        )
        message = self._extract_llm_final_message(llm_resp) or "Чем могу помочь?"
        resp = self._done_message_response(req, message)
        return {"response": resp}

    async def _node_scenario_where_my_flight(self, state: OrchestratorState) -> dict[str, Any]:
        req = state["req"]
        pending = req.runtime.pending if isinstance(req.runtime.pending, dict) else {}
        prior_extracted = pending.get("extracted") if isinstance(pending.get("extracted"), dict) else {}

        params_resp = await self._call_llm(
            parent=req,
            mode="tool_params",
            input_data={
                "task": FLIGHT_TOOL_PARAMS_TASK_RU,
                "user_message": req.text,
                "tool_name": "get_flight_status",
                "tool_schema": FLIGHT_TOOL_SCHEMA,
            },
            constraints={"temperature": 0},
        )

        parsed = self._normalize_tool_params(params_resp, fallback_tool_name="get_flight_status")
        merged = self._merge_non_empty_params(prior_extracted, parsed.get("extracted") if isinstance(parsed.get("extracted"), dict) else {})

        has_flight = isinstance(merged.get("flight_number"), str) and bool(str(merged.get("flight_number")).strip())
        has_last = isinstance(merged.get("last_name"), str) and bool(str(merged.get("last_name")).strip())

        if not (has_flight or has_last):
            prompt = str(parsed.get("prompt") or FLIGHT_ASK_INPUT_DEFAULT_RU).strip() or FLIGHT_ASK_INPUT_DEFAULT_RU
            pending_state = {
                "type": "tool_params",
                "scenario_id": SC_WHERE_MY_FLIGHT,
                "tool_name": "get_flight_status",
                "extracted": merged,
                "missing": ["flight_number_or_last_name"],
                "prompt": prompt,
            }
            resp = N8nRunResponse(
                trace_id=req.trace_id,
                correlation_id=req.correlation_id,
                request_id=req.request_id,
                session_id=req.session_id,
                ts_ms=now_ts_ms(),
                status="PARTIAL",
                result=prompt,
                client_handler={"command": "ASK_USER_INPUT", "payload": {"message": prompt}},
                next_runtime=self._next_runtime(
                    req,
                    active_workflow_id=SC_WHERE_MY_FLIGHT,
                    pending=pending_state,
                    context=req.runtime.context,
                ),
            )
            return {"response": resp}

        tool_args: dict[str, Any] = {}
        if has_flight:
            tool_args["flight_number"] = str(merged["flight_number"]).strip()
        if has_last:
            tool_args["last_name"] = str(merged["last_name"]).strip()

        tool_resp = await self._call_tool(parent=req, tool_name="get_flight_status", args=tool_args)
        if not tool_resp.ok:
            msg = FLIGHT_NOT_FOUND_MESSAGE_RU if (tool_resp.error and tool_resp.error.code == "not_found") else "Не удалось получить статус рейса. Попробуйте позже."
            if tool_resp.error and tool_resp.error.code != "not_found":
                resp = self._failed_response(
                    req,
                    code=tool_resp.error.code,
                    message=msg,
                    next_runtime=self._next_runtime(req),
                    client_handler={"command": "SHOW_ERROR_MESSAGE", "payload": {"message": msg, "code": tool_resp.error.code}},
                )
            else:
                resp = self._done_message_response(req, msg)
            return {"response": resp}

        tool_results = [{"tool_name": "get_flight_status", "result": tool_resp.data}]
        final_resp = await self._call_llm(
            parent=req,
            mode="final_response",
            input_data={
                "task": FLIGHT_FINAL_TASK_RU,
                "user_message": req.text,
                "tool_results": tool_results,
                "scenario_context": FLIGHT_SCENARIO_CONTEXT_RU,
            },
            constraints={"temperature": 0.1},
        )
        message = self._extract_llm_final_message(final_resp) or self._format_flight_status_from_tool(tool_resp.data)
        resp = self._done_message_response(req, message)
        return {"response": resp}

    async def _node_scenario_find_nearest_airport(self, state: OrchestratorState) -> dict[str, Any]:
        req = state["req"]

        pos_resp = await self._call_tool(parent=req, tool_name="get_current_position", args={})
        if not pos_resp.ok:
            msg = "Не удалось получить текущую позицию."
            resp = self._failed_response(
                req,
                code=(pos_resp.error.code if pos_resp.error else "tool_failed"),
                message=msg,
                next_runtime=self._next_runtime(req),
                client_handler={"command": "SHOW_ERROR_MESSAGE", "payload": {"message": msg}},
            )
            return {"response": resp}

        tool_results: list[dict[str, Any]] = [{"tool_name": "get_current_position", "result": pos_resp.data}]

        search_params_llm = await self._call_llm(
            parent=req,
            mode="tool_params",
            input_data={
                "task": AIRPORT_SEARCH_PARAMS_TASK_RU,
                "user_message": req.text,
                "tool_name": "search_airports_nearby",
                "tool_schema": AIRPORT_SEARCH_TOOL_SCHEMA,
                "tool_results": tool_results,
            },
            constraints={"temperature": 0},
        )
        search_params = self._normalize_tool_params(search_params_llm, fallback_tool_name="search_airports_nearby").get("extracted") or {}
        if not isinstance(search_params, dict):
            search_params = {}
        city = str(search_params.get("city") or "").strip()
        radius_raw = search_params.get("radius_km", 50)
        try:
            radius_km = float(radius_raw)
        except Exception:
            radius_km = 50.0
        if not city:
            pos_data = self._extract_nested_data(pos_resp.data)
            city = str((pos_data or {}).get("city") or "Moscow").strip() or "Moscow"

        search_resp = await self._call_tool(
            parent=req,
            tool_name="search_airports_nearby",
            args={"city": city, "radius_km": radius_km},
        )
        if not search_resp.ok:
            msg = "Не удалось найти ближайшие аэропорты."
            resp = self._failed_response(
                req,
                code=(search_resp.error.code if search_resp.error else "tool_failed"),
                message=msg,
                next_runtime=self._next_runtime(req),
                client_handler={"command": "SHOW_ERROR_MESSAGE", "payload": {"message": msg}},
            )
            return {"response": resp}

        tool_results.append({"tool_name": "search_airports_nearby", "result": search_resp.data})

        build_params_llm = await self._call_llm(
            parent=req,
            mode="tool_params",
            input_data={
                "task": AIRPORT_ROUTE_PARAMS_TASK_RU,
                "user_message": req.text,
                "tool_name": "build_route",
                "tool_schema": AIRPORT_ROUTE_TOOL_SCHEMA,
                "tool_results": tool_results,
            },
            constraints={"temperature": 0},
        )
        route_params = self._normalize_tool_params(build_params_llm, fallback_tool_name="build_route").get("extracted") or {}
        if not isinstance(route_params, dict):
            route_params = {}

        route_args = self._normalize_route_args(route_params, pos_resp.data, search_resp.data)
        if route_args is None:
            msg = "Не удалось собрать координаты для построения маршрута."
            resp = self._failed_response(
                req,
                code="route_params_missing",
                message=msg,
                next_runtime=self._next_runtime(req),
                client_handler={"command": "SHOW_ERROR_MESSAGE", "payload": {"message": msg}},
            )
            return {"response": resp}

        route_resp = await self._call_tool(parent=req, tool_name="build_route", args=route_args)
        if not route_resp.ok:
            msg = "Не удалось построить маршрут до аэропорта."
            resp = self._failed_response(
                req,
                code=(route_resp.error.code if route_resp.error else "tool_failed"),
                message=msg,
                next_runtime=self._next_runtime(req),
                client_handler={"command": "SHOW_ERROR_MESSAGE", "payload": {"message": msg}},
            )
            return {"response": resp}

        tool_results.append({"tool_name": "build_route", "result": route_resp.data})

        final_llm = await self._call_llm(
            parent=req,
            mode="final_response",
            input_data={
                "task": AIRPORT_FINAL_TASK_RU,
                "user_message": req.text,
                "tool_results": tool_results,
                "scenario_context": AIRPORT_SCENARIO_CONTEXT_RU,
            },
            constraints={"temperature": 0.1},
        )

        message = self._extract_llm_final_message(final_llm) or self._format_nearest_airport_from_tools(tool_results)

        pos_data = self._extract_nested_data(pos_resp.data) or {}
        search_data = self._extract_nested_data(search_resp.data) or {}
        route_data = self._extract_nested_data(route_resp.data) or {}
        client_events = [
            {"command": "SET_POSITION", "payload": {"data": {"current_position": pos_data}}},
            {"command": "SET_AIRPORTS", "payload": {"data": {"airports": search_data.get("airports", [])}}},
            {"command": "BUILD_ROUTE", "payload": {"data": {"route": route_data}}},
        ]

        resp = self._done_message_response(req, message, client_events=client_events)
        return {"response": resp}

    async def _call_llm(
        self,
        *,
        parent: N8nRunRequest,
        mode: str,
        input_data: dict[str, Any],
        constraints: dict[str, Any] | None = None,
    ) -> LlmResponse:
        req = LlmRequest(
            trace_id=parent.trace_id,
            correlation_id=parent.correlation_id,
            request_id=uuid4(),
            session_id=parent.session_id,
            ts_ms=now_ts_ms(),
            mode=mode,  # type: ignore[arg-type]
            input=input_data,
            constraints=constraints or {},
        )
        raw = await self._request_json(
            f"{self.llm_subject_prefix}{self.user_id}",
            req.model_dump_json().encode("utf-8"),
        )
        return LlmResponse.model_validate(raw)

    async def _call_tool(
        self,
        *,
        parent: N8nRunRequest,
        tool_name: str,
        args: dict[str, Any],
    ) -> ToolCallResponse:
        req = ToolCallRequest(
            trace_id=parent.trace_id,
            correlation_id=parent.correlation_id,
            request_id=uuid4(),
            session_id=parent.session_id,
            ts_ms=now_ts_ms(),
            tool_name=tool_name,
            args=args,
        )
        raw = await self._request_json(
            f"{self.tools_subject_prefix}{tool_name}",
            req.model_dump_json().encode("utf-8"),
        )
        return ToolCallResponse.model_validate(raw)

    async def _request_json(self, subject: str, payload: bytes) -> dict[str, Any]:
        if self._nc is None:
            raise RuntimeError("NATS is not connected")
        msg = await self._nc.request(subject, payload, timeout=self.request_timeout_s)
        data = json.loads(msg.data.decode("utf-8"))
        if not isinstance(data, dict):
            raise RuntimeError(f"Invalid JSON response from {subject}")
        return data

    def _done_message_response(
        self,
        req: N8nRunRequest,
        message: str,
        *,
        client_events: list[dict[str, Any]] | None = None,
    ) -> N8nRunResponse:
        clean = message.strip() if isinstance(message, str) else ""
        if not clean:
            clean = "Готово."
        return N8nRunResponse(
            trace_id=req.trace_id,
            correlation_id=req.correlation_id,
            request_id=req.request_id,
            session_id=req.session_id,
            ts_ms=now_ts_ms(),
            status="DONE",
            result=clean,
            client_handler={"command": "SHOW_MESSAGE", "payload": {"message": clean}},
            client_events=client_events or [],
            next_runtime=self._next_runtime(req),
        )

    def _failed_response(
        self,
        req: N8nRunRequest,
        *,
        code: str,
        message: str,
        next_runtime: N8nRuntimeState,
        client_handler: dict[str, Any] | None = None,
    ) -> N8nRunResponse:
        return N8nRunResponse(
            trace_id=req.trace_id,
            correlation_id=req.correlation_id,
            request_id=req.request_id,
            session_id=req.session_id,
            ts_ms=now_ts_ms(),
            status="FAILED",
            result="",
            client_handler=client_handler or {},
            next_runtime=next_runtime,
            errors=[ErrorInfo(code=code, message=message)],
        )

    def _next_runtime(
        self,
        req: N8nRunRequest,
        *,
        active_workflow_id: str | None = None,
        pending: dict[str, Any] | None = None,
        context: dict[str, Any] | None = None,
    ) -> N8nRuntimeState:
        return N8nRuntimeState(
            active_workflow_id=active_workflow_id,
            pending=pending,
            context=context,
            version=req.runtime.version,
        )

    @staticmethod
    def _is_explicit_echo(text: str) -> bool:
        return bool(re.match(r"^\s*(echo|эхо)\b", text or "", flags=re.IGNORECASE))

    @staticmethod
    def _echo_payload_text(text: str) -> str:
        stripped = str(text or "").strip()
        return re.sub(r"^\s*(echo|эхо)\b[:\s-]*", "", stripped, flags=re.IGNORECASE).strip()

    @staticmethod
    def _extract_llm_final_message(llm_resp: LlmResponse) -> str | None:
        if not llm_resp.ok or not isinstance(llm_resp.data, dict):
            return None
        value = llm_resp.data.get("response_text")
        if isinstance(value, str) and value.strip():
            return value.strip()
        return None

    @staticmethod
    def _normalize_tool_params(llm_resp: LlmResponse, *, fallback_tool_name: str) -> dict[str, Any]:
        if not llm_resp.ok or not isinstance(llm_resp.data, dict):
            if fallback_tool_name == "get_flight_status":
                return {"extracted": {}, "missing": ["flight_number_or_last_name"], "prompt": FLIGHT_ASK_INPUT_DEFAULT_RU}
            return {"extracted": {}, "missing": [], "prompt": None}
        data = dict(llm_resp.data)
        extracted = data.get("extracted")
        if not isinstance(extracted, dict):
            extracted = {}
        missing = data.get("missing")
        if not isinstance(missing, list):
            missing = []
        prompt = data.get("prompt")
        if prompt is not None and not isinstance(prompt, str):
            prompt = str(prompt)
        return {"extracted": extracted, "missing": [str(m) for m in missing], "prompt": prompt}

    @staticmethod
    def _merge_non_empty_params(base: dict[str, Any], new_values: dict[str, Any]) -> dict[str, Any]:
        merged = dict(base or {})
        for key, value in (new_values or {}).items():
            if value is None:
                continue
            if isinstance(value, str) and not value.strip():
                continue
            merged[key] = value
        return merged

    @staticmethod
    def _extract_nested_data(tool_call_data: Any) -> dict[str, Any] | None:
        if not isinstance(tool_call_data, dict):
            return None
        inner = tool_call_data.get("data")
        if isinstance(inner, dict):
            return inner
        return None

    @staticmethod
    def _normalize_route_args(
        extracted: dict[str, Any],
        pos_tool_data: Any,
        airports_tool_data: Any,
    ) -> dict[str, float] | None:
        def _to_float(value: Any) -> float | None:
            if isinstance(value, (int, float)):
                return float(value)
            if isinstance(value, str):
                try:
                    return float(value.strip())
                except Exception:
                    return None
            return None

        out: dict[str, float] = {}
        for key in ("from_lat", "from_lon", "to_lat", "to_lon"):
            val = _to_float(extracted.get(key))
            if val is not None:
                out[key] = val

        pos = LangGraphWorkflowService._extract_nested_data(pos_tool_data) or {}
        if "from_lat" not in out:
            v = _to_float(pos.get("lat"))
            if v is not None:
                out["from_lat"] = v
        if "from_lon" not in out:
            v = _to_float(pos.get("lon"))
            if v is not None:
                out["from_lon"] = v

        airports_data = LangGraphWorkflowService._extract_nested_data(airports_tool_data) or {}
        airports = airports_data.get("airports") if isinstance(airports_data.get("airports"), list) else []
        first = airports[0] if airports and isinstance(airports[0], dict) else {}
        if "to_lat" not in out:
            v = _to_float(first.get("lat"))
            if v is not None:
                out["to_lat"] = v
        if "to_lon" not in out:
            v = _to_float(first.get("lon"))
            if v is not None:
                out["to_lon"] = v

        required = ("from_lat", "from_lon", "to_lat", "to_lon")
        if not all(k in out for k in required):
            return None
        return {k: out[k] for k in required}

    @staticmethod
    def _format_flight_status_from_tool(tool_call_data: Any) -> str:
        data = LangGraphWorkflowService._extract_nested_data(tool_call_data) or {}
        flight = data.get("flight") if isinstance(data.get("flight"), dict) else {}
        if not flight:
            return FLIGHT_NOT_FOUND_MESSAGE_RU

        fn = str(flight.get("flight_number") or "рейс").strip()
        src = str(flight.get("from") or "?").strip()
        dst = str(flight.get("to") or "?").strip()
        dep = str(flight.get("departure_time") or "").strip()
        arr = str(flight.get("arrival_time") or "").strip()
        gate = str(flight.get("gate") or "").strip()
        terminal = str(flight.get("terminal") or "").strip()
        status = str(flight.get("status") or "").strip().upper()
        status_map = {
            "ON_TIME": "вовремя",
            "DELAYED": "задерживается",
            "CANCELLED": "отменен",
            "BOARDING": "идет посадка",
            "LANDED": "прибыл",
        }
        status_ru = status_map.get(status, status.lower() if status else "неизвестен")

        dep_short = dep[11:16] if len(dep) >= 16 and "T" in dep else dep
        arr_short = arr[11:16] if len(arr) >= 16 and "T" in arr else arr

        parts = [f"Рейс {fn} ({src} → {dst})"]
        if dep_short or arr_short:
            timing = []
            if dep_short:
                timing.append(f"вылет {dep_short}")
            if arr_short:
                timing.append(f"прибытие {arr_short}")
            parts.append(", ".join(timing))
        parts.append(f"Статус: {status_ru}.")
        if gate or terminal:
            extra = []
            if gate:
                extra.append(f"гейт {gate}")
            if terminal:
                extra.append(f"терминал {terminal}")
            parts.append(", ".join(extra).capitalize() + ".")
        return " ".join(parts)

    @staticmethod
    def _format_nearest_airport_from_tools(tool_results: list[dict[str, Any]]) -> str:
        pos: dict[str, Any] = {}
        airports: list[dict[str, Any]] = []
        route: dict[str, Any] = {}

        for item in tool_results:
            if not isinstance(item, dict):
                continue
            name = str(item.get("tool_name") or "")
            result = LangGraphWorkflowService._extract_nested_data(item.get("result")) or {}
            if name == "get_current_position":
                pos = result
            elif name == "search_airports_nearby":
                airports = result.get("airports") if isinstance(result.get("airports"), list) else []
            elif name == "build_route":
                route = result

        first = airports[0] if airports and isinstance(airports[0], dict) else {}
        city = str(pos.get("city") or "вашего местоположения").strip()
        airport_name = str(first.get("name") or first.get("code") or "аэропорт").strip()
        airport_code = str(first.get("code") or "").strip()
        airport_dist = first.get("distance_km")
        route_dist = route.get("distance_km")

        msg = f"Найден ближайший аэропорт рядом с {city}: {airport_name}"
        if airport_code:
            msg += f" ({airport_code})"
        details = []
        if isinstance(airport_dist, (int, float)):
            details.append(f"до аэропорта ~{float(airport_dist):.1f} км")
        if isinstance(route_dist, (int, float)):
            details.append(f"длина маршрута ~{float(route_dist):.1f} км")
        if details:
            msg += ". " + ", ".join(details).capitalize() + "."
        return msg
