from __future__ import annotations

import asyncio
import json
import os
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


@dataclass(frozen=True)
class Env:
    user_id: str
    nats_url: str
    agent_subject: str
    workflow_health_subject: str


def _env() -> Env:
    user_id = os.getenv("USER_ID", "user123")
    nats_url = os.getenv("NATS_URL", "nats://nats:4222")
    agent_subject = os.getenv("NATS_AGENT_SUBJECT", Subjects.AGENT_PREFIX) + user_id
    workflow_health_subject = os.getenv("NATS_WORKFLOW_HEALTH_SUBJECT", Subjects.WORKFLOW_HEALTH)
    return Env(
        user_id=user_id,
        nats_url=nats_url,
        agent_subject=agent_subject,
        workflow_health_subject=workflow_health_subject,
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


async def test_where_my_flight(nc: NATS, subject: str) -> None:
    resp = await _agent_request(nc, subject=subject, text="где рейс SU123")
    _assert_show_message(resp)


async def test_find_nearest_airport(nc: NATS, subject: str) -> None:
    resp = await _agent_request(nc, subject=subject, text="найди ближайший аэропорт")
    _assert_show_message(resp)
    commands = [e.get("command") for e in (resp.client_events or []) if isinstance(e, dict)]
    expected = {"SET_POSITION", "SET_AIRPORTS", "BUILD_ROUTE"}
    _assert(expected.issubset(set(str(c) for c in commands)), "nearest_airport must return map events")


async def main() -> None:
    env = _env()
    nc = NATS()
    await nc.connect(servers=[env.nats_url], name="src_e2e", max_reconnect_attempts=-1)
    try:
        await _wait_for_runtime(nc, env.workflow_health_subject, timeout_s=90)
        await test_echo(nc, env.agent_subject)
        await test_free_speech(nc, env.agent_subject)
        await test_where_my_flight(nc, env.agent_subject)
        await test_find_nearest_airport(nc, env.agent_subject)
        print("E2E OK")
    finally:
        await nc.drain()
        await nc.close()


if __name__ == "__main__":
    asyncio.run(main())
