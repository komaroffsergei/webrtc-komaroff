import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from uuid import uuid4

from src_agent.settings import AGENT_MAX_STEPS, CHITCHAT_FALLBACK_MESSAGE, SYSTEM_PROMPT, TIMEOUT_SECONDS

from src_agent.utils.mcp_tools import AgentResponse
from src_agent.utils.nats_logger import NatsLogger

from src_agent.utils.db import (
    Database,
    log_event,
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
    select_scenario_tool,
)
from src_agent.settings import PARAMS_SYSTEM_PROMPT_TEMPLATE, ROUTING_SYSTEM_PROMPT

logger = logging.getLogger("src_agent.agent")

def _collapse_blank_lines(text: str) -> str:
    out = text
    while "\n\n\n" in out:
        out = out.replace("\n\n\n", "\n\n")
    return out


def _strip_tag_blocks(text: str, *, start_tag: str, end_tag: str) -> tuple[str, list[str]]:
    if not text:
        return "", []

    remaining = text
    extracted: list[str] = []
    start_lower = start_tag.lower()
    end_lower = end_tag.lower()

    while True:
        lower = remaining.lower()
        start = lower.find(start_lower)
        if start < 0:
            break
        end = lower.find(end_lower, start + len(start_lower))
        if end < 0:
            inner = remaining[start + len(start_tag):]
            extracted.append(inner.strip())
            remaining = remaining[:start]
            break
        inner = remaining[start + len(start_tag):end]
        extracted.append(inner.strip())
        remaining = remaining[:start] + remaining[end + len(end_tag):]

    return remaining, [x for x in extracted if x]


def _split_think(text: str) -> tuple[str, str]:
    cleaned, chunks = _strip_tag_blocks(text, start_tag="<think>", end_tag="</think>")
    cleaned = _collapse_blank_lines(cleaned).strip()
    thought = "\n\n".join(chunks).strip()
    return cleaned, thought

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

def _truncate_text(text: str, limit: int = 160) -> str:
    """Trims and truncates text to a given limit, adding ellipsis if needed."""
    s = " ".join((text or "").split()).strip()
    if len(s) > limit:
        return s[: limit - 3] + "..."
    return s


def _sanitize_user_visible_container(container: object) -> tuple[object, str]:
    think_parts: list[str] = []

    def walk(obj: object, key: str | None = None) -> object:
        if isinstance(obj, dict):
            for k, v in list(obj.items()):
                obj[k] = walk(v, k)
            return obj
        if isinstance(obj, list):
            for i, v in enumerate(obj):
                obj[i] = walk(v, key)
            return obj
        if isinstance(obj, str) and key in ("result", "prompt", "hint", "summary", "text", "message", "content"):
            cleaned, thought = _split_think(obj)
            if thought:
                think_parts.append(thought)
            return cleaned
        return obj

    updated = walk(container)
    combined = "\n\n".join([t for t in think_parts if t]).strip()
    return updated, combined


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

    async def _emit_thought(
        self,
        *,
        summary: str,
        content: str,
        title: Optional[str] = None,
        scenario_id: str | None = None,
        scenario_reason: str | None = None,
        tools: list[str] | None = None,
    ) -> None:
        if not self._events:
            return
        data: dict[str, object] = {"summary": summary, "content": content}
        if title is not None:
            data["title"] = title
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
        request_id = str(uuid4())

        await log_event(
            self.db,
            session_id=session_id,
            request_id=request_id,
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

        scenario_state = state.get("scenario")
        if not isinstance(scenario_state, dict):
            scenario_state = {"id": None, "status": "RUNNING", "input": None}
            state["scenario"] = scenario_state
        current_scenario_id = scenario_state.get("id")
        pending = state.get("pending")
        has_pending = (
            isinstance(pending, dict)
            and isinstance(pending.get("scenario_id"), str)
            and bool(pending.get("scenario_id"))
        ) or (
            scenario_state.get("status") == "NEEDS_INPUT"
            and isinstance(scenario_state.get("id"), str)
            and bool(scenario_state.get("id"))
        )
        if (
            not isinstance(pending, dict)
            and scenario_state.get("status") == "NEEDS_INPUT"
            and isinstance(scenario_state.get("id"), str)
            and bool(scenario_state.get("id"))
        ):
            state["pending"] = {"scenario_id": scenario_state.get("id")}
            pending = state["pending"]
        selected_scenario_id: str | None = None
        selected_reason: str | None = None
        invalid_routing_tool_calls = False
        routing_model: str | None = None

        if has_pending:
            selected_scenario_id = scenario_state.get("id") if isinstance(scenario_state.get("id"), str) else None
            if not selected_scenario_id and isinstance(pending, dict) and isinstance(pending.get("scenario_id"), str):
                selected_scenario_id = pending.get("scenario_id")
            selected_reason = "pending_input"
            if selected_scenario_id:
                scenario_state["id"] = selected_scenario_id
        else:
            turns = state.get("turns") if isinstance(state.get("turns"), list) else []
            recent = turns[-8:] if len(turns) > 8 else turns
            routing_messages = [{"role": "system", "content": ROUTING_SYSTEM_PROMPT}]
            routing_messages.append({
                "role": "system",
                "content": json.dumps(
                    {
                        "context": {
                            "current_scenario_id": current_scenario_id,
                            "current_scenario_status": scenario_state.get("status"),
                            "pending": {
                                "active": isinstance(state.get("pending"), dict),
                                "scenario_id": (state.get("pending") or {}).get("scenario_id") if isinstance(state.get("pending"), dict) else None,
                            },
                        }
                    },
                    ensure_ascii=False,
                ),
            })
            for t in recent:
                role = t.get("role")
                text = t.get("text")
                if role in ("user", "assistant") and isinstance(text, str) and text.strip():
                    routing_messages.append({"role": role, "content": text})
            routing_payload = {
                "messages": routing_messages,
                "tools": [build_select_scenario_tool_schema()],
                "think": False,
                "options": {"temperature": 0.0},
            }
            await log_event(
                self.db,
                session_id=session_id,
                request_id=request_id,
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

            def _pick_scenario(calls: list[dict]) -> tuple[str | None, str | None]:
                for call in calls:
                    fn_name = call.get("function", {}).get("name")
                    if fn_name != "select_scenario":
                        continue
                    raw_args = call.get("function", {}).get("arguments") or {}
                    selected = select_scenario_tool(raw_args)
                    sid = selected.get("scenario_id")
                    reason = selected.get("reason")
                    return (sid if isinstance(sid, str) else None, reason if isinstance(reason, str) else None)
                return None, None

            attempts: list[dict] = [
                {"label": "base", "system_suffix": ""},
                {
                    "label": "strict",
                    "system_suffix": (
                        "\n\nКРИТИЧНО: вызови ТОЛЬКО select_scenario в формате <tool_call>..</tool_call>. "
                        "Любой другой tool-call запрещён.\n"
                        "Если не подходит ни один сценарий — не вызывай инструменты и верни пустой content."
                    ),
                },
                {
                    "label": "example",
                    "system_suffix": (
                        "\n\nПРИМЕР:\n"
                        "<tool_call>{\"name\":\"select_scenario\",\"arguments\":{\"scenario_id\":\"flight_status\",\"reason\":\"user asks for flight status\"}}</tool_call>\n"
                        "Выводи только tool-call или пустой content."
                    ),
                },
            ]

            routing_resp: dict = {}
            tool_calls: list[dict] = []
            for attempt in attempts:
                attempt_messages = list(routing_messages)
                attempt_messages[0] = {
                    "role": "system",
                    "content": ROUTING_SYSTEM_PROMPT + attempt["system_suffix"],
                }
                attempt_payload = dict(routing_payload)
                attempt_payload["messages"] = attempt_messages
                try:
                    routing_resp = await self._request_llm(attempt_payload)
                except Exception as exc:
                    await log_event(
                        self.db,
                        session_id=session_id,
                        request_id=request_id,
                        role="SYSTEM",
                        event_type="ERROR",
                        output={"type": "LLM_EXCEPTION", "message": str(exc), "step": 0, "label": attempt["label"]},
                    )
                    continue

                routing_model = routing_resp.get("model")
                routing_msg = routing_resp.get("message") or {}
                tool_calls = routing_msg.get("tool_calls") or []
                selected_scenario_id, selected_reason = _pick_scenario(tool_calls)
                if selected_scenario_id:
                    break
                if tool_calls:
                    invalid_routing_tool_calls = True

            await log_event(
                self.db,
                session_id=session_id,
                request_id=request_id,
                role="LLM",
                event_type="ROUTING_RESPONSE",
                output={
                    "tool_calls": [{"name": c.get("function", {}).get("name")} for c in tool_calls],
                    "content_preview": _preview_text((routing_resp.get("message") or {}).get("content"), 300),
                    "model": routing_model,
                },
            )
            logger.info(
                "ROUTING LLM response tools=%s content=%s",
                ",".join(c.get("function", {}).get("name") or "" for c in tool_calls),
                _preview_text((routing_resp.get("message") or {}).get("content"), 120),
            )

            if routing_resp.get("error"):
                await log_event(
                    self.db,
                    session_id=session_id,
                    request_id=request_id,
                    role="SYSTEM",
                    event_type="ERROR",
                    output={
                        "type": "LLM_EXCEPTION",
                        "message": routing_resp.get("details") or routing_resp.get("error"),
                        "step": 0,
                        "model": routing_model,
                    },
                )
                await update_session_status(self.db, session_id=session_id, status="FAILED")
                return self._error(
                    "LLM_EXCEPTION",
                    routing_resp.get("details") or routing_resp.get("error"),
                    prompt=prompt,
                    steps=0,
                    model=routing_model,
                    total_time=None,
                    session_id=session_id,
                )

            if selected_scenario_id is None and invalid_routing_tool_calls:
                error_text = "Routing model returned unsupported tool calls."
                await log_event(
                    self.db,
                    session_id=session_id,
                    request_id=request_id,
                    role="SYSTEM",
                    event_type="ERROR",
                    output={"type": "ROUTING_INVALID_TOOL_CALLS"},
                )
                await update_session_status(self.db, session_id=session_id, status="FAILED")
                return self._error(
                    "UNSUPPORTED_REQUEST",
                    error_text,
                    prompt=prompt,
                    steps=0,
                    model=routing_model,
                    total_time=None,
                    session_id=session_id,
                )
            if selected_scenario_id and not get_scenario(selected_scenario_id):
                error_text = f"Unknown scenario: {selected_scenario_id}"
                await log_event(
                    self.db,
                    session_id=session_id,
                    request_id=request_id,
                    role="SYSTEM",
                    event_type="ERROR",
                    output={"type": "UNKNOWN_SCENARIO", "scenario_id": selected_scenario_id},
                )
                await update_session_status(self.db, session_id=session_id, status="FAILED")
                return self._error(
                    "UNSUPPORTED_REQUEST",
                    error_text,
                    prompt=prompt,
                    steps=0,
                    model=routing_model,
                    total_time=None,
                    session_id=session_id,
                )

        if selected_scenario_id:
            kind = "SCENARIO_SELECTED"
            if current_scenario_id and selected_scenario_id != current_scenario_id:
                kind = "SCENARIO_SWITCHED"
                scenario_state["input"] = None
            scenario_state["id"] = selected_scenario_id
            scenario_state["status"] = "RUNNING"
            if not has_pending:
                state.setdefault("scenario_artifacts", {}).pop(selected_scenario_id, None)
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
            # Chitchat should not persist artifacts across turns.
            state.setdefault("scenario_artifacts", {}).pop("chitchat", None)

        state["scenario"] = scenario_state

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
            bool(state.get("pending")),
            json.dumps((state.get("scenario") or {}).get("input"), ensure_ascii=False),
        )
        if scenario and selected_scenario_id != "chitchat":
            if scenario.input_hints:
                llm_prompt = getattr(scenario, "llm_prompt", None)
                if not isinstance(llm_prompt, str) or not llm_prompt.strip():
                    raise RuntimeError(f"Scenario is missing llm_prompt: {scenario.id}")
                params_prompt = PARAMS_SYSTEM_PROMPT_TEMPLATE.format(
                    scenario_id=scenario.id,
                    llm_prompt=llm_prompt.strip(),
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
                    request_id=request_id,
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
                        request_id=request_id,
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
                    request_id=request_id,
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
                db=self.db,
                llm_request=self._request_llm,
                request_id=request_id,
            )
            if scenario_response:
                extracted_think = ""
                updated_response, extracted_think = _sanitize_user_visible_container(scenario_response)
                scenario_response = updated_response if isinstance(updated_response, dict) else scenario_response

                if state.get("turns") and state["turns"][-1].get("role") == "assistant":
                    last_text = state["turns"][-1].get("text")
                    if isinstance(last_text, str):
                        cleaned_turn, thought_turn = _split_think(last_text)
                        state["turns"][-1]["text"] = cleaned_turn
                        if thought_turn:
                            extracted_think = f"{extracted_think}\n\n{thought_turn}".strip() if extracted_think else thought_turn

                if selected_scenario_id == "chitchat":
                    result = scenario_response.get("result")
                    if isinstance(result, str) and not result.strip():
                        scenario_response["result"] = CHITCHAT_FALLBACK_MESSAGE
                        handler = scenario_response.get("client_handler")
                        if isinstance(handler, dict):
                            artifacts = handler.get("artifacts")
                            if isinstance(artifacts, dict):
                                payload = artifacts.get("payload")
                                if isinstance(payload, dict):
                                    for v in payload.values():
                                        if not isinstance(v, dict):
                                            continue
                                        if isinstance(v.get("summary"), str) and not v["summary"].strip():
                                            v["summary"] = CHITCHAT_FALLBACK_MESSAGE
                                        data = v.get("data")
                                        if isinstance(data, dict) and isinstance(data.get("text"), str) and not data["text"].strip():
                                            data["text"] = CHITCHAT_FALLBACK_MESSAGE
                        if state.get("turns") and (state["turns"][-1].get("role") == "assistant"):
                            state["turns"][-1]["text"] = CHITCHAT_FALLBACK_MESSAGE

                if extracted_think and self._events:
                    await self._emit_thought(
                        summary="...Thinking",
                        content=_truncate_text(extracted_think, 200),
                        title=extracted_think,
                        scenario_id=selected_scenario_id,
                        scenario_reason=selected_reason,
                    )

                if scenario_state.get("status") != "NEEDS_INPUT":
                    state["pending"] = None
                    scenario_state["input"] = None
                    state["scenario"] = {"id": None, "status": "RUNNING", "input": None}
                else:
                    if not isinstance(state.get("pending"), dict):
                        state["pending"] = {"scenario_id": selected_scenario_id}
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
                    request_id=request_id,
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
                    request_id=request_id,
                    role="SYSTEM",
                    event_type="SCENARIO_LOG",
                    output={"entries": state.get("scenario_log", [])},
                )

                status = "RUNNING" if scenario_state.get("status") == "NEEDS_INPUT" else "DONE"
                await update_session_status(self.db, session_id=session_id, status=status)

                return scenario_response

        error_text = "Scenario handler did not produce a response."
        await log_event(
            self.db,
            session_id=session_id,
            request_id=request_id,
            role="SYSTEM",
            event_type="ERROR",
            output={"type": "SCENARIO_NO_RESPONSE", "message": error_text},
        )
        await update_session_status(self.db, session_id=session_id, status="FAILED")
        return self._error(
            "SCENARIO_NO_RESPONSE",
            error_text,
            prompt=prompt,
            steps=0,
            model=None,
            total_time=None,
            session_id=session_id,
        )
