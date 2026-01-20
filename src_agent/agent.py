import json
import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from uuid import uuid4

from src_agent.settings import AGENT_MAX_STEPS, SYSTEM_PROMPT, TIMEOUT_SECONDS
from src_agent.tools.tools import *  # noqa: F403

from src_agent.utils.helpers import normalize_args
from src_agent.utils.mcp_tools import (
    REGISTRY,
    AgentResponse,
    AGentClientCommands,
    AgentClientHandler,
    AgentRegistry,
)
from src_agent.utils.nats_logger import NatsLogger

from src_agent.utils.db import (
    Database,
    log_event,
    save_artifact,
    create_intent,
    finish_intent,
    update_session_status,
    get_conversation,
    save_conversation,
    init_conversation,
    add_turn,
    truncate_conversation_after_turn,
)

from src_agent.scenarios.registry import (
    build_extract_params_tool_schema,
    build_select_scenario_tool_schema,
    get_scenario,
    list_selectable_scenarios,
    select_scenario_tool,
)
from src_agent.settings import PARAMS_SYSTEM_PROMPT_TEMPLATE, ROUTING_SYSTEM_PROMPT

logger = logging.getLogger("src_agent.agent")


def _preview_text(s: Any, limit: int) -> Optional[str]:
    if s is None:
        return None
    if not isinstance(s, str):
        s = str(s)
    return s[:limit]


def _safe_llm_messages(messages: list[dict], preview_limit: int = 200) -> list[dict]:
    out: list[dict] = []
    for m in messages:
        content = m.get("content")
        out.append({
            "role": m.get("role"),
            "len": len(content) if isinstance(content, str) else None,
            "preview": _preview_text(content, preview_limit) if isinstance(content, str) else None,
            "tool_name": m.get("tool_name"),
        })
    return out


def _safe_llm_payload(payload: dict, preview_limit: int = 200) -> dict:
    messages = payload.get("messages") or []
    tools = payload.get("tools") or []
    tool_names: list[str] = []
    for t in tools:
        name = (t.get("function") or {}).get("name")
        if name:
            tool_names.append(name)
    return {
        "message_count": len(messages) if isinstance(messages, list) else 0,
        "messages": _safe_llm_messages(messages, preview_limit) if isinstance(messages, list) else [],
        "tools": tool_names,
        "think": payload.get("think"),
        "options": payload.get("options"),
    }


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _build_messages_from_turns(turns: list[dict]) -> list[dict]:
    messages: list[dict] = [{"role": "system", "content": "\n".join(SYSTEM_PROMPT)}]
    for t in turns:
        role = t.get("role")
        text = t.get("text")
        if role in ("user", "assistant") and isinstance(text, str):
            messages.append({"role": role, "content": text})
    return messages


def _log_scenario_event(
    state: dict,
    *,
    scenario_id: str | None,
    status: str,
    kind: str,
    data: dict,
    turn_id: str | None,
) -> None:
    state.setdefault("scenario_log", []).append({
        "ts": _now_iso(),
        "scenario_id": scenario_id,
        "status": status,
        "kind": kind,
        "data": data,
        "turn_id": turn_id,
    })


class MCPAgent:
    def __init__(
        self,
        nc,
        *,
        llm_subject: str,
        max_steps: int = AGENT_MAX_STEPS,
        timeout_seconds: int = TIMEOUT_SECONDS,
        events: NatsLogger | None = None,
        db: Database,
        user_id: str,
    ):
        self.nc = nc
        self.llm_subject = llm_subject
        self.max_steps = max_steps
        self.timeout_seconds = timeout_seconds
        self._events = events

        self.db = db
        self.user_id = user_id

        self.tools = [v["schema"] for v in REGISTRY.values()]
        self.tools_impl = {k: v["fn"] for k, v in REGISTRY.items()}

    async def _emit_thought(
        self,
        *,
        summary: str,
        content: str,
        scenario_id: str | None = None,
        scenario_reason: str | None = None,
        tools: list[str] | None = None,
    ) -> None:
        if not self._events:
            return
        data: dict[str, object] = {"summary": summary, "content": content}
        if scenario_id:
            scenario: dict[str, object] = {"id": scenario_id}
            if scenario_reason:
                scenario["reason"] = scenario_reason
            data["scenario"] = scenario
        if tools:
            data["tools"] = tools
        await self._events.log("command", "thought", data)

    async def _request_llm(self, payload: dict) -> dict:
        logger.info("LLM request payload=%s", json.dumps(_safe_llm_payload(payload), ensure_ascii=False))
        msg = await self.nc.request(
            self.llm_subject,
            json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            timeout=self.timeout_seconds,
        )
        data = json.loads(msg.data.decode("utf-8"))
        message = data.get("message") or {}
        tool_calls = message.get("tool_calls") or []
        logger.info(
            "LLM response model=%s tools=%s content=%s",
            data.get("model"),
            ",".join((c.get("function") or {}).get("name") or "" for c in tool_calls),
            _preview_text(message.get("content"), 200),
        )
        return data

    def _error(
        self,
        error_type: str,
        message: str | None,
        *,
        prompt: str,
        steps: int,
        model: str | None,
        total_time: float | None = None,
        session_id: str | None = None,
    ) -> AgentResponse:
        data = {
            "model": model or "unknown",
            "prompt": prompt,
            "steps": steps,
        }
        if total_time is not None:
            data["total_time_sec"] = round(total_time, 3)
        error = {"type": error_type}
        if message:
            error["message"] = message
        resp: AgentResponse = {
            "success": False,
            "error": error,
            "data": data,
            "client_handler": {"command": "SHOW_ERROR_MESSAGE"},
        }
        if session_id:
            resp["session_id"] = session_id
        return resp

    async def run(self, *, prompt: str, session_id: str, edit: dict | None = None) -> AgentResponse:
        logger.info("[USER] %s", prompt)
        reset_artifacts()  # noqa: F405

        # intent is still hardcoded
        intent_id = await create_intent(self.db, session_id=session_id, intent_type="DEFAULT")

        await log_event(
            self.db,
            session_id=session_id,
            intent_id=intent_id,
            role="USER",
            event_type="MESSAGE",
            input={"text": prompt},
        )

        state = get_conversation(session_id)
        if state is None:
            state = init_conversation(session_id)

        turn_id: str | None = None
        edit_turn_id = edit.get("turn_id") if isinstance(edit, dict) else None
        if edit_turn_id:
            applied = truncate_conversation_after_turn(state, edit_turn_id)
            if applied:
                for t in state.get("turns", []):
                    if t.get("turn_id") == edit_turn_id:
                        t["text"] = prompt
                        t["ts"] = _now_iso()
                        turn_id = edit_turn_id
                        break
                _log_scenario_event(
                    state,
                    scenario_id=(state.get("scenario") or {}).get("id"),
                    status="RUNNING",
                    kind="EDIT_APPLIED",
                    data={"turn_id": edit_turn_id},
                    turn_id=edit_turn_id,
                )
            else:
                turn_id = add_turn(state, role="user", text=prompt)
        else:
            turn_id = add_turn(state, role="user", text=prompt)

        state["messages"] = _build_messages_from_turns(state.get("turns", []))

        scenario_state = state.get("scenario") or {"id": None, "status": "RUNNING", "pending": None, "input": None}
        current_scenario_id = scenario_state.get("id")
        has_pending = bool(scenario_state.get("pending"))
        selected_scenario_id: str | None = None
        selected_reason: str | None = None

        if has_pending and current_scenario_id:
            scenario_state["input"] = None
            selected_scenario_id = current_scenario_id
        else:
            routing_messages = [
                {
                    "role": "system",
                    "content": ROUTING_SYSTEM_PROMPT,
                },
                {"role": "user", "content": prompt},
            ]
            routing_payload = {
                "messages": routing_messages,
                "tools": [build_select_scenario_tool_schema()],
                "think": False,
                "options": {"temperature": 0.0},
            }
            await log_event(
                self.db,
                session_id=session_id,
                intent_id=intent_id,
                role="LLM",
                event_type="ROUTING_REQUEST",
                input={
                    "tools": ["select_scenario"],
                    "messages": _safe_llm_messages(routing_messages, preview_limit=200),
                    "options": {"temperature": 0.0},
                },
            )
            logger.info(
                "ROUTING LLM request tools=select_scenario messages=%d user=%s",
                len(routing_messages),
                _preview_text(prompt, 120),
            )
            try:
                routing_resp = await self._request_llm(routing_payload)
            except Exception as exc:
                await log_event(
                    self.db,
                    session_id=session_id,
                    intent_id=intent_id,
                    role="SYSTEM",
                    event_type="ERROR",
                    output={"type": "LLM_EXCEPTION", "message": str(exc), "step": 0},
                )
                await finish_intent(self.db, intent_id=intent_id, status="FAILED")
                await update_session_status(self.db, session_id=session_id, status="FAILED")
                return self._error(
                    "LLM_EXCEPTION",
                    str(exc),
                    prompt=prompt,
                    steps=0,
                    model=None,
                    total_time=None,
                    session_id=session_id,
                )

            routing_msg = routing_resp.get("message") or {}
            tool_calls = routing_msg.get("tool_calls") or []
            scenario_ids = {s.id for s in list_selectable_scenarios()}
            await log_event(
                self.db,
                session_id=session_id,
                intent_id=intent_id,
                role="LLM",
                event_type="ROUTING_RESPONSE",
                output={
                    "tool_calls": [{"name": c.get("function", {}).get("name")} for c in tool_calls],
                    "content_preview": _preview_text(routing_msg.get("content"), 300),
                    "model": routing_resp.get("model"),
                },
            )
            logger.info(
                "ROUTING LLM response tools=%s content=%s",
                ",".join(c.get("function", {}).get("name") or "" for c in tool_calls),
                _preview_text(routing_msg.get("content"), 120),
            )
            if routing_resp.get("error"):
                await log_event(
                    self.db,
                    session_id=session_id,
                    intent_id=intent_id,
                    role="SYSTEM",
                    event_type="ERROR",
                    output={
                        "type": "LLM_EXCEPTION",
                        "message": routing_resp.get("details") or routing_resp.get("error"),
                        "step": 0,
                        "model": routing_resp.get("model"),
                    },
                )
                await finish_intent(self.db, intent_id=intent_id, status="FAILED")
                await update_session_status(self.db, session_id=session_id, status="FAILED")
                return self._error(
                    "LLM_EXCEPTION",
                    routing_resp.get("details") or routing_resp.get("error"),
                    prompt=prompt,
                    steps=0,
                    model=routing_resp.get("model"),
                    total_time=None,
                    session_id=session_id,
                )

            for call in tool_calls:
                fn_name = call.get("function", {}).get("name")
                if fn_name in scenario_ids:
                    selected_scenario_id = fn_name
                    selected_reason = "routing_tool_name"
                    break
                if fn_name != "select_scenario":
                    continue
                raw_args = call.get("function", {}).get("arguments") or {}
                selected = select_scenario_tool(raw_args)
                selected_scenario_id = selected.get("scenario_id")
                selected_reason = selected.get("reason")
                break

        if selected_scenario_id:
            kind = "SCENARIO_SELECTED"
            if current_scenario_id and selected_scenario_id != current_scenario_id:
                kind = "SCENARIO_SWITCHED"
                scenario_state["pending"] = None
                scenario_state["input"] = None
            scenario_state["id"] = selected_scenario_id
            scenario_state["status"] = "RUNNING"
            _log_scenario_event(
                state,
                scenario_id=selected_scenario_id,
                status="RUNNING",
                kind=kind,
                data={"from": current_scenario_id, "to": selected_scenario_id, "reason": selected_reason},
                turn_id=turn_id,
            )
        else:
            selected_scenario_id = "chitchat"
            if current_scenario_id != selected_scenario_id:
                scenario_state["pending"] = None
                scenario_state["input"] = None
                scenario_state["id"] = selected_scenario_id
                scenario_state["status"] = "RUNNING"
            _log_scenario_event(
                state,
                scenario_id=selected_scenario_id,
                status="RUNNING",
                kind="SCENARIO_FALLBACK_CHITCHAT",
                data={"from": current_scenario_id},
                turn_id=turn_id,
            )

        state["scenario"] = scenario_state
        save_conversation(state)

        scenario = get_scenario(selected_scenario_id)
        await self._emit_thought(
            summary="Scenario selected",
            content="Starting scenario handler.",
            scenario_id=selected_scenario_id,
            scenario_reason=selected_reason,
        )
        logger.info(
            "SCENARIO start id=%s pending=%s input=%s",
            selected_scenario_id,
            bool((state.get("scenario") or {}).get("pending")),
            json.dumps((state.get("scenario") or {}).get("input"), ensure_ascii=False),
        )
        if scenario and not has_pending and selected_scenario_id != "chitchat":
            if scenario.input_hints:
                params_prompt = PARAMS_SYSTEM_PROMPT_TEMPLATE.format(
                    scenario_id=scenario.id,
                    title=scenario.title,
                    description=scenario.description,
                )
                params_messages = [
                    {"role": "system", "content": params_prompt},
                    {"role": "user", "content": prompt},
                ]
                params_payload = {
                    "messages": params_messages,
                    "tools": [build_extract_params_tool_schema(scenario)],
                    "think": False,
                    "options": {"temperature": 0.0},
                }
                logger.info(
                    "PARAMS LLM request scenario=%s payload=%s",
                    scenario.id,
                    json.dumps(_safe_llm_payload(params_payload), ensure_ascii=False),
                )
                await log_event(
                    self.db,
                    session_id=session_id,
                    intent_id=intent_id,
                    role="LLM",
                    event_type="PARAMS_REQUEST",
                    input={
                        "scenario_id": scenario.id,
                        "messages": _safe_llm_messages(params_messages, preview_limit=200),
                    },
                )
                try:
                    params_resp = await self._request_llm(params_payload)
                except Exception as exc:
                    await log_event(
                        self.db,
                        session_id=session_id,
                        intent_id=intent_id,
                        role="SYSTEM",
                        event_type="ERROR",
                        output={"type": "LLM_EXCEPTION", "message": str(exc), "step": 0},
                    )
                    params_resp = {}

                params_msg = params_resp.get("message") or {}
                params_tool_calls = params_msg.get("tool_calls") or []
                logger.info(
                    "PARAMS LLM response scenario=%s tools=%s content=%s",
                    scenario.id,
                    ",".join((c.get("function") or {}).get("name") or "" for c in params_tool_calls),
                    _preview_text(params_msg.get("content"), 200),
                )
                await log_event(
                    self.db,
                    session_id=session_id,
                    intent_id=intent_id,
                    role="LLM",
                    event_type="PARAMS_RESPONSE",
                    output={
                        "scenario_id": scenario.id,
                        "tool_calls": [{"name": c.get("function", {}).get("name")} for c in params_tool_calls],
                        "content_preview": _preview_text(params_msg.get("content"), 200),
                    },
                )

                for call in params_tool_calls:
                    if call.get("function", {}).get("name") != "extract_params":
                        continue
                    raw_args = call.get("function", {}).get("arguments") or {}
                    scenario_state["input"] = raw_args
                    break

        if scenario:
            scenario_response = await scenario.handle(
                state,
                prompt=prompt,
                turn_id=turn_id or str(uuid4()),
                session_id=session_id,
                intent_id=intent_id,
                db=self.db,
                llm_request=self._request_llm,
            )
            if scenario_response:
                scenario_state["input"] = None
                scenario_response["session_id"] = session_id
                state["messages"] = _build_messages_from_turns(state.get("turns", []))
                save_conversation(state)
                logger.info(
                    "SCENARIO response id=%s status=%s command=%s result=%s",
                    selected_scenario_id,
                    scenario_state.get("status"),
                    (scenario_response.get("client_handler") or {}).get("command"),
                    _preview_text(scenario_response.get("result"), 200),
                )

                await log_event(
                    self.db,
                    session_id=session_id,
                    intent_id=intent_id,
                    role="SYSTEM",
                    event_type="SCENARIO_RESPONSE",
                    output={
                        "scenario_id": selected_scenario_id,
                        "status": scenario_state.get("status"),
                        "client_handler": (scenario_response.get("client_handler") or {}).get("command"),
                    },
                )
                await log_event(
                    self.db,
                    session_id=session_id,
                    intent_id=intent_id,
                    role="SYSTEM",
                    event_type="SCENARIO_LOG",
                    output={"entries": state.get("scenario_log", [])},
                )

                status = "RUNNING" if scenario_state.get("status") == "NEEDS_INPUT" else "DONE"
                await finish_intent(self.db, intent_id=intent_id, status=status)
                await update_session_status(self.db, session_id=session_id, status=status)

                return scenario_response

        messages = state.get("messages") or _build_messages_from_turns(state.get("turns", []))

        last_client_handler: AGentClientCommands | None = None
        last_provided_artifacts: list[str] = []
        model_used = None
        tools_used: list[str] = []
        start_ts = time.perf_counter()

        try:
            for step in range(1, self.max_steps + 1):
                step_started = time.perf_counter()
                logger.info("STEP %d started", step)
                await self._emit_thought(
                    summary=f"Step {step}/{self.max_steps}",
                    content="Waiting for LLM response.",
                    scenario_id=selected_scenario_id,
                    scenario_reason=selected_reason,
                    tools=tools_used,
                )

                await log_event(
                    self.db,
                    session_id=session_id,
                    intent_id=intent_id,
                    role="SYSTEM",
                    event_type="STEP_START",
                    input={"step": step},
                )

                llm_payload = {
                    "messages": messages,
                    "tools": self.tools,
                    "think": False,
                    "options": {"temperature": 0.0},
                }
                last_user = next(
                    (m.get("content") for m in reversed(messages) if m.get("role") == "user"),
                    None,
                )
                logger.info(
                    "STEP %d LLM request tools=%s messages=%d last_user=%s",
                    step,
                    ",".join(t["function"]["name"] for t in self.tools),
                    len(messages),
                    _preview_text(last_user, 120),
                )

                # safe llm request log
                await log_event(
                    self.db,
                    session_id=session_id,
                    intent_id=intent_id,
                    role="LLM",
                    event_type="LLM_REQUEST",
                    input={
                        "step": step,
                        "tools": [t["function"]["name"] for t in self.tools],
                        "messages": _safe_llm_messages(messages, preview_limit=200),
                        "options": {"temperature": 0.0},
                    },
                )

                try:
                    resp = await self._request_llm(llm_payload)
                except Exception as exc:
                    await log_event(
                        self.db,
                        session_id=session_id,
                        intent_id=intent_id,
                        role="SYSTEM",
                        event_type="ERROR",
                        output={"type": "LLM_EXCEPTION", "message": str(exc), "step": step},
                    )
                    await finish_intent(self.db, intent_id=intent_id, status="FAILED")
                    await update_session_status(self.db, session_id=session_id, status="FAILED")
                    total_time = time.perf_counter() - start_ts
                    return self._error(
                        "LLM_EXCEPTION",
                        str(exc),
                        prompt=prompt,
                        steps=step,
                        model=model_used,
                        total_time=total_time,
                        session_id=session_id,
                    )

                if resp.get("error"):
                    await log_event(
                        self.db,
                        session_id=session_id,
                        intent_id=intent_id,
                        role="SYSTEM",
                        event_type="ERROR",
                        output={
                            "type": "LLM_EXCEPTION",
                            "message": resp.get("details") or resp.get("error"),
                            "step": step,
                            "model": resp.get("model") or model_used,
                        },
                    )
                    await finish_intent(self.db, intent_id=intent_id, status="FAILED")
                    await update_session_status(self.db, session_id=session_id, status="FAILED")
                    total_time = time.perf_counter() - start_ts
                    return self._error(
                        "LLM_EXCEPTION",
                        resp.get("details") or resp.get("error"),
                        prompt=prompt,
                        steps=step,
                        model=resp.get("model") or model_used,
                        total_time=total_time,
                        session_id=session_id,
                    )

                msg = resp.get("message") or {}
                model_used = resp.get("model") or model_used
                tool_calls = msg.get("tool_calls") or [{"function": {"name": "no_tool_calls", "arguments": {}}}]
                content_preview = _preview_text(msg.get("content"), 120)

                logger.info(
                    "STEP %d llm_time=%.3fs tools=%s content=%s",
                    step,
                    time.perf_counter() - step_started,
                    ",".join(call["function"]["name"] for call in tool_calls),
                    content_preview,
                )

                await log_event(
                    self.db,
                    session_id=session_id,
                    intent_id=intent_id,
                    role="LLM",
                    event_type="LLM_RESPONSE",
                    output={
                        "step": step,
                        "model": model_used,
                        "tool_calls": [{"name": c["function"]["name"]} for c in tool_calls],
                        "content_preview": _preview_text(msg.get("content"), 300),
                    },
                )

                for call in tool_calls:
                    name = call["function"]["name"]
                    raw_args = call["function"].get("arguments") or {}
                    if name not in tools_used:
                        tools_used.append(name)
                    await self._emit_thought(
                        summary=f"Step {step}/{self.max_steps}",
                        content=f"Executing tool: {name}.",
                        scenario_id=selected_scenario_id,
                        scenario_reason=selected_reason,
                        tools=tools_used,
                    )

                    logger.info(
                        "STEP %d tool_call=%s args=%s",
                        step,
                        name,
                        json.dumps(raw_args, ensure_ascii=False),
                    )

                    try:
                        safe_args = normalize_args(self.tools_impl[name], raw_args)
                    except Exception as exc:
                        await log_event(
                            self.db,
                            session_id=session_id,
                            intent_id=intent_id,
                            role="SYSTEM",
                            event_type="ERROR",
                            name=name,
                            output={"type": "TOOLS_EXCEPTION", "message": f"normalize_args: {exc}", "step": step},
                        )
                        await finish_intent(self.db, intent_id=intent_id, status="FAILED")
                        await update_session_status(self.db, session_id=session_id, status="FAILED")
                        total_time = time.perf_counter() - start_ts
                        return self._error(
                            "TOOLS_EXCEPTION",
                            str(exc),
                            prompt=prompt,
                            steps=step,
                            model=model_used,
                            total_time=total_time,
                            session_id=session_id,
                        )

                    logger.info(
                        "STEP %d tool_call_normalized=%s args=%s",
                        step,
                        name,
                        json.dumps(safe_args, ensure_ascii=False),
                    )
                    await log_event(
                        self.db,
                        session_id=session_id,
                        intent_id=intent_id,
                        role="TOOL",
                        event_type="TOOL_CALL",
                        name=name,
                        input={"step": step, "args": safe_args},
                    )

                    try:
                        cont, result = self.tools_impl[name](**safe_args)
                    except Exception as exc:
                        logger.info("STEP %d tool_error=%s error=%s", step, name, str(exc))
                        await log_event(
                            self.db,
                            session_id=session_id,
                            intent_id=intent_id,
                            role="SYSTEM",
                            event_type="ERROR",
                            name=name,
                            output={"type": "TOOLS_EXCEPTION", "message": str(exc), "step": step},
                        )
                        await finish_intent(self.db, intent_id=intent_id, status="FAILED")
                        await update_session_status(self.db, session_id=session_id, status="FAILED")
                        total_time = time.perf_counter() - start_ts
                        return self._error(
                            "TOOLS_EXCEPTION",
                            str(exc),
                            prompt=prompt,
                            steps=step,
                            model=model_used,
                            total_time=total_time,
                            session_id=session_id,
                        )

                    tool_meta: AgentRegistry = REGISTRY.get(name, {})
                    if tool_meta.get("client_handler"):
                        last_client_handler = tool_meta["client_handler"]
                        last_provided_artifacts = list(tool_meta.get("provides") or [])

                    logger.info(
                        "STEP %d tool_result=%s cont=%s status=%s time=%.3fs response=%s",
                        step,
                        name,
                        cont,
                        result.get("status"),
                        time.perf_counter() - step_started,
                        json.dumps(result, ensure_ascii=False),
                    )

                    await log_event(
                        self.db,
                        session_id=session_id,
                        intent_id=intent_id,
                        role="TOOL",
                        event_type="TOOL_RESULT",
                        name=name,
                        output={
                            "step": step,
                            "status": result.get("status"),
                            "preview": _preview_text(json.dumps(result, ensure_ascii=False), 800),
                        },
                    )

                    if not cont and result.get("status") == "ok":
                        total_time = time.perf_counter() - start_ts

                        artifacts_payload: Dict[str, Any] = {
                            key: ARTIFACTS[key]  # noqa: F405
                            for key in last_provided_artifacts
                            if key in ARTIFACTS  # noqa: F405
                        }

                        # persist artifacts
                        for k, v in artifacts_payload.items():
                            await save_artifact(
                                self.db,
                                session_id=session_id,
                                intent_id=intent_id,
                                type="AGENT_ARTIFACT",
                                name=k,
                                data=v if isinstance(v, dict) else {"value": v},
                            )

                        client_handler: AgentClientHandler | None = None
                        if last_client_handler:
                            client_handler = {
                                "command": last_client_handler,
                                "artifacts": {
                                    "last": last_provided_artifacts[0] if last_provided_artifacts else None,
                                    "all": last_provided_artifacts,
                                    "payload": artifacts_payload,
                                },
                            }

                        await log_event(
                            self.db,
                            session_id=session_id,
                            intent_id=intent_id,
                            role="SYSTEM",
                            event_type="FINAL_RESPONSE",
                            output={
                                "success": True,
                                "steps": step,
                                "model": model_used or "unknown",
                                "client_handler": last_client_handler,
                                "provided_artifacts": last_provided_artifacts,
                                "total_time_sec": round(total_time, 3),
                            },
                        )

                        await finish_intent(self.db, intent_id=intent_id, status="DONE")
                        await update_session_status(self.db, session_id=session_id, status="DONE")

                        if client_handler and client_handler.get("command") in ("ASK_USER_INPUT", "SHOW_MESSAGE"):
                            artifacts = (client_handler.get("artifacts") or {}).get("payload") or {}
                            last_key = (client_handler.get("artifacts") or {}).get("last")
                            payload = artifacts.get(last_key) if last_key else None
                            message_text = None
                            if isinstance(payload, dict):
                                for key in ("message", "summary", "prompt"):
                                    if isinstance(payload.get(key), str):
                                        message_text = payload[key]
                                        break
                            if not message_text and isinstance(result.get("result"), str):
                                message_text = result.get("result")
                            if message_text:
                                add_turn(state, role="assistant", text=message_text)

                        state["messages"] = _build_messages_from_turns(state.get("turns", []))
                        save_conversation(state)

                        return {
                            "success": True,
                            "data": {
                                "model": model_used or "unknown",
                                "prompt": prompt,
                                "steps": step,
                                "total_time_sec": round(total_time, 3),
                            },
                            "session_id": session_id,
                            "result": result.get("result"),
                            "client_handler": client_handler,
                        }

                    # continue conversation for next loop
                    artifact_keys: list[str] = []
                    if isinstance(result.get("artifact_key"), str):
                        artifact_keys = [result["artifact_key"]]
                    elif last_provided_artifacts:
                        artifact_keys = list(last_provided_artifacts)

                    ack_parts = [f"Tool {name} executed."]
                    if artifact_keys:
                        ack_parts.append(f"Result stored as artifact(s): {', '.join(artifact_keys)}.")
                    if result.get("status") and result.get("status") != "ok":
                        ack_parts.append(f"Status: {result.get('status')}.")

                    messages.append({
                        "role": "system",
                        "content": " ".join(ack_parts),
                    })

                    if not cont:
                        break

            # max steps exceeded
            total_time = time.perf_counter() - start_ts
            await log_event(
                self.db,
                session_id=session_id,
                intent_id=intent_id,
                role="SYSTEM",
                event_type="ERROR",
                output={
                    "type": "MAX_STEPS_EXCEEDED",
                    "steps": self.max_steps,
                    "model": model_used or "unknown",
                    "total_time_sec": round(total_time, 3),
                },
            )
            await finish_intent(self.db, intent_id=intent_id, status="FAILED")
            await update_session_status(self.db, session_id=session_id, status="FAILED")
            return self._error(
                "MAX_STEPS_EXCEEDED",
                None,
                prompt=prompt,
                steps=self.max_steps,
                model=model_used,
                total_time=total_time,
                session_id=session_id,
            )

        except Exception as exc:
            # last-resort: if something failed outside expected flow
            total_time = time.perf_counter() - start_ts
            await log_event(
                self.db,
                session_id=session_id,
                intent_id=intent_id,
                role="SYSTEM",
                event_type="ERROR",
                output={"type": "AGENT_EXCEPTION", "message": str(exc), "total_time_sec": round(total_time, 3)},
            )
            await finish_intent(self.db, intent_id=intent_id, status="FAILED")
            await update_session_status(self.db, session_id=session_id, status="FAILED")
            return self._error(
                "AGENT_EXCEPTION",
                str(exc),
                prompt=prompt,
                steps=0,
                model=model_used,
                total_time=total_time,
                session_id=session_id,
            )
