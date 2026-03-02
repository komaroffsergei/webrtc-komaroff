from __future__ import annotations

import asyncio
import json
import os
import re
import time
from dataclasses import dataclass
from uuid import UUID, uuid4

from nats.aio.client import Client as NATS

from src_shared.contracts import (
    AgentInboundRequest,
    AgentInboundResponse,
    ServiceHealthRequest,
    ServiceHealthResponse,
    now_ts_ms,
)
from src_shared.contracts.subjects import Subjects

_YEAR_RE = re.compile(r"\b(1[6-9]\d{2}|20\d{2}|21\d{2})\b")
_CONTEXT_REFUSAL_RE = re.compile(
    r"(в текущих данных нет|нет подтвержденной информации|данных о годе|могу помочь с тем, что известно в текущем диалоге)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Env:
    user_id: str
    nats_url: str
    agent_subject: str
    workflow_health_subject: str
    events_subject: str


def _env() -> Env:
    user_id = os.getenv("USER_ID", "user123")
    nats_url = os.getenv("NATS_URL", "nats://nats:4222")
    agent_subject = os.getenv("NATS_AGENT_SUBJECT", Subjects.AGENT_PREFIX) + user_id
    workflow_health_subject = os.getenv("NATS_WORKFLOW_HEALTH_SUBJECT", Subjects.WORKFLOW_HEALTH)
    events_subject = os.getenv("NATS_EVENTS_SUBJECT", Subjects.EVENTS_PREFIX) + user_id
    return Env(
        user_id=user_id,
        nats_url=nats_url,
        agent_subject=agent_subject,
        workflow_health_subject=workflow_health_subject,
        events_subject=events_subject,
    )


def _assert(cond: bool, message: str) -> None:
    if not cond:
        raise AssertionError(message)


async def _wait_for_runtime(nc: NATS, subject: str, timeout_s: float = 60.0) -> None:
    deadline = time.monotonic() + timeout_s
    while True:
        try:
            req = ServiceHealthRequest(
                trace_id=uuid4(),
                correlation_id=None,
                request_id=uuid4(),
                session_id=None,
                ts_ms=now_ts_ms(),
            )
            msg = await nc.request(subject, req.model_dump_json().encode("utf-8"), timeout=2)
            resp = ServiceHealthResponse.model_validate(json.loads(msg.data.decode("utf-8")))
            if resp.ok:
                return
        except Exception:
            pass
        if time.monotonic() >= deadline:
            raise TimeoutError(f"Timed out waiting for health subject: {subject}")
        await asyncio.sleep(1)


async def _agent_request(
    nc: NATS,
    *,
    subject: str,
    text: str,
    session_id: UUID | None = None,
) -> AgentInboundResponse:
    req = AgentInboundRequest(
        trace_id=uuid4(),
        correlation_id=None,
        request_id=uuid4(),
        session_id=session_id,
        ts_ms=now_ts_ms(),
        text=text,
        edit=None,
    )
    msg = await nc.request(subject, req.model_dump_json().encode("utf-8"), timeout=120)
    return AgentInboundResponse.model_validate(json.loads(msg.data.decode("utf-8")))


def _assert_show_message(resp: AgentInboundResponse) -> None:
    _assert(resp.ok is True, "response.ok must be true")
    _assert(resp.status == "DONE", f"response.status must be DONE, got: {resp.status}")
    _assert(isinstance(resp.client_handler, dict), "client_handler must be dict")
    _assert(resp.client_handler.get("command") == "SHOW_MESSAGE", "client_handler.command must be SHOW_MESSAGE")


async def test_echo(nc: NATS, subject: str) -> None:
    resp = await _agent_request(nc, subject=subject, text="echo тест")
    _assert_show_message(resp)
    message = str((resp.client_handler.get("payload") or {}).get("message") or "")
    _assert("тест" in message.lower(), "echo response must include input text")


async def test_free_speech(nc: NATS, subject: str) -> None:
    resp = await _agent_request(nc, subject=subject, text="как дела")
    _assert_show_message(resp)


async def test_llm_debug_includes_model(nc: NATS, env: Env) -> None:
    marker = f"debug-model-{uuid4().hex[:8]}"
    sub = await nc.subscribe(env.events_subject)
    try:
        resp = await _agent_request(nc, subject=env.agent_subject, text=marker)
        _assert_show_message(resp)

        deadline = time.monotonic() + 20.0
        expected_model = os.getenv("LLM_REMOTE_MODEL", "qwen3:30b")
        while time.monotonic() < deadline:
            try:
                msg = await sub.next_msg(timeout=1.0)
            except Exception:
                continue
            event = json.loads(msg.data.decode("utf-8"))
            if not isinstance(event, dict):
                continue
            if event.get("service") != "src_llm" or event.get("name") != "llm_request_debug":
                continue
            data = event.get("data") if isinstance(event.get("data"), dict) else {}
            payload = data.get("payload") if isinstance(data.get("payload"), dict) else {}
            input_payload = payload.get("input") if isinstance(payload.get("input"), dict) else {}
            user_message = str(input_payload.get("user_message") or input_payload.get("text") or "")
            if marker not in user_message:
                continue

            runtime = payload.get("runtime") if isinstance(payload.get("runtime"), dict) else {}
            configured_model = str(runtime.get("configured_model") or "")
            _assert(configured_model == expected_model, f"configured_model must be {expected_model}, got: {configured_model}")
            return
        raise AssertionError("did not receive llm_request_debug event with configured_model")
    finally:
        await sub.unsubscribe()


async def test_where_my_flight(nc: NATS, subject: str) -> None:
    resp = await _agent_request(nc, subject=subject, text="где рейс SU123")
    _assert_show_message(resp)


async def test_where_my_flight_pending_exit(nc: NATS, subject: str) -> None:
    first = await _agent_request(nc, subject=subject, text="где мой рейс")
    _assert(first.ok is True, "first pending response must be ok")
    _assert(first.status == "PARTIAL", f"expected PARTIAL on first turn, got {first.status}")
    command = str((first.client_handler or {}).get("command") or "")
    _assert(command == "ASK_USER_INPUT", f"expected ASK_USER_INPUT, got {command}")
    _assert(first.session_id is not None, "session_id must be present for pending follow-up")

    second = await _agent_request(nc, subject=subject, text="как дела", session_id=first.session_id)
    _assert(second.ok is True, "second response must be ok")
    _assert(second.status == "DONE", f"expected DONE after pending escape, got {second.status}")
    second_command = str((second.client_handler or {}).get("command") or "")
    _assert(second_command == "SHOW_MESSAGE", f"expected SHOW_MESSAGE after pending escape, got {second_command}")


async def test_find_nearest_airport(nc: NATS, subject: str) -> None:
    resp = await _agent_request(nc, subject=subject, text="найди ближайший аэропорт")
    _assert_show_message(resp)
    commands = [e.get("command") for e in (resp.client_events or []) if isinstance(e, dict)]
    expected = {"SET_POSITION", "SET_AIRPORTS", "BUILD_ROUTE"}
    _assert(expected.issubset(set(str(c) for c in commands)), "nearest_airport must return map events")


async def test_airport_followup_uses_context(nc: NATS, subject: str) -> None:
    first = await _agent_request(nc, subject=subject, text="найди аэропорт")
    _assert_show_message(first)
    _assert(first.session_id is not None, "session_id must be present for follow-up")

    second = await _agent_request(
        nc,
        subject=subject,
        text="кем и когда был основан каждый из этих аэропортов",
        session_id=first.session_id,
    )
    _assert_show_message(second)
    text = str((second.client_handler or {}).get("payload", {}).get("message") or "").lower()
    _assert(not _CONTEXT_REFUSAL_RE.search(text), "follow-up should not fallback to context-only refusal")
    _assert("шереметьево" in text, "follow-up should include airports from previous context")
    _assert(bool(_YEAR_RE.search(text)), "follow-up should include explicit years")
    _assert("уточните, о каком объекте" not in text, "plural follow-up must not ask for entity clarification")


async def test_airport_followup_singular_resolves_focus(nc: NATS, subject: str) -> None:
    first = await _agent_request(nc, subject=subject, text="найди аэропорт")
    _assert_show_message(first)
    _assert(first.session_id is not None, "session_id must be present for follow-up")

    second = await _agent_request(
        nc,
        subject=subject,
        text="в каком году он построен",
        session_id=first.session_id,
    )
    _assert_show_message(second)
    text = str((second.client_handler or {}).get("payload", {}).get("message") or "").lower()
    _assert("шереметьево" in text, "singular follow-up should resolve to focused entity from previous answer")
    _assert(not _CONTEXT_REFUSAL_RE.search(text), "singular follow-up should not fallback to context-only refusal")
    _assert(bool(_YEAR_RE.search(text)), "singular follow-up should include explicit year")
    _assert("уточните, о каком объекте" not in text, "singular follow-up should not ask clarification when focus is resolvable")


async def main() -> None:
    env = _env()
    nc = NATS()
    await nc.connect(servers=[env.nats_url], name="src_e2e", max_reconnect_attempts=-1)
    try:
        await _wait_for_runtime(nc, env.workflow_health_subject, timeout_s=90)
        await test_llm_debug_includes_model(nc, env)
        await test_echo(nc, env.agent_subject)
        await test_free_speech(nc, env.agent_subject)
        await test_where_my_flight(nc, env.agent_subject)
        await test_where_my_flight_pending_exit(nc, env.agent_subject)
        await test_find_nearest_airport(nc, env.agent_subject)
        await test_airport_followup_uses_context(nc, env.agent_subject)
        await test_airport_followup_singular_resolves_focus(nc, env.agent_subject)
        print("E2E OK")
    finally:
        await nc.drain()
        await nc.close()


if __name__ == "__main__":
    asyncio.run(main())
