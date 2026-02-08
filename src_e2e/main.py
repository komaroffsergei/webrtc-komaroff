from __future__ import annotations

import asyncio
import json
import os
import time
from dataclasses import dataclass
from typing import Any
from uuid import UUID, uuid4

import asyncpg
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
    database_url: str
    agent_subject: str
    n8n_health_subject: str


def _env() -> Env:
    user_id = os.getenv("USER_ID", "user123")
    nats_url = os.getenv("NATS_URL", "nats://nats:4222")
    database_url = os.getenv("DATABASE_URL", "postgresql://mcp:mcp_pass@src_postgres:5432/mcp")
    agent_subject = os.getenv("NATS_AGENT_SUBJECT", Subjects.AGENT_PREFIX) + user_id
    n8n_health_subject = os.getenv("NATS_N8N_HEALTH_SUBJECT", Subjects.N8N_HEALTH)
    return Env(
        user_id=user_id,
        nats_url=nats_url,
        database_url=database_url,
        agent_subject=agent_subject,
        n8n_health_subject=n8n_health_subject,
    )


async def _wait_for_n8n_bridge(nc: NATS, subject: str, timeout_s: float = 60.0) -> None:
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
    request_id: UUID | None = None,
    trace_id: UUID | None = None,
) -> AgentInboundResponse:
    req = AgentInboundRequest(
        trace_id=trace_id or uuid4(),
        correlation_id=None,
        request_id=request_id or uuid4(),
        session_id=session_id,
        ts_ms=now_ts_ms(),
        text=text,
        edit=None,
    )
    msg = await nc.request(subject, req.model_dump_json().encode("utf-8"), timeout=120)
    return AgentInboundResponse.model_validate(json.loads(msg.data.decode("utf-8")))


def _assert(cond: bool, message: str) -> None:
    if not cond:
        raise AssertionError(message)


def test_contracts_roundtrip() -> None:
    req = AgentInboundRequest(
        trace_id=uuid4(),
        correlation_id=None,
        request_id=uuid4(),
        session_id=None,
        ts_ms=now_ts_ms(),
        text="hello",
        edit=None,
    )
    req2 = AgentInboundRequest.model_validate_json(req.model_dump_json())
    _assert(req2.text == "hello", "AgentInboundRequest roundtrip failed")

    resp = AgentInboundResponse(
        trace_id=req.trace_id,
        correlation_id=req.correlation_id,
        request_id=req.request_id,
        session_id=None,
        ts_ms=now_ts_ms(),
        ok=True,
        status="DONE",
        result="",
        client_handler={"command": "SHOW_MESSAGE", "payload": {"message": "ok"}},
        client_events=[],
        errors=[],
    )
    resp2 = AgentInboundResponse.model_validate_json(resp.model_dump_json())
    _assert(resp2.status == "DONE", "AgentInboundResponse roundtrip failed")


async def _assert_runtime_requests_row(pg: asyncpg.Pool, request_id: UUID, expected_status: str | None = None) -> None:
    async with pg.acquire() as conn:
        row = await conn.fetchrow(
            "select request_id, status, response from runtime_requests where request_id = $1",
            request_id,
        )
        _assert(row is not None, f"runtime_requests row missing for request_id={request_id}")
        if expected_status is not None:
            _assert(row["status"] == expected_status, f"runtime_requests status mismatch: {row['status']}")


async def test_echo_idempotent(nc: NATS, pg: asyncpg.Pool, subject: str) -> None:
    session_id = uuid4()
    request_id = uuid4()
    trace_id = uuid4()

    r1 = await _agent_request(
        nc,
        subject=subject,
        text="hello",
        session_id=session_id,
        request_id=request_id,
        trace_id=trace_id,
    )
    _assert(r1.ok is True, "echo request should be ok")
    _assert(r1.status == "DONE", f"echo status should be DONE, got {r1.status}")
    _assert(isinstance(r1.client_handler, dict), "echo client_handler must be a dict")
    _assert(r1.client_handler.get("command") == "SHOW_MESSAGE", "echo must return SHOW_MESSAGE")

    await _assert_runtime_requests_row(pg, request_id, expected_status="DONE")

    r2 = await _agent_request(
        nc,
        subject=subject,
        text="hello",
        session_id=session_id,
        request_id=request_id,
        trace_id=trace_id,
    )
    for key in ("ok", "status", "result", "client_handler", "client_events", "errors", "session_id", "trace_id", "request_id"):
        _assert(getattr(r2, key) == getattr(r1, key), f"duplicate request_id mismatch for field={key}")

    await _assert_runtime_requests_row(pg, request_id, expected_status="DONE")


async def test_collect_name(nc: NATS, subject: str) -> None:
    session_id = uuid4()

    r1 = await _agent_request(nc, subject=subject, text="name", session_id=session_id)
    _assert(r1.ok is True, "collect_name first call should be ok (RUNNING)")
    _assert(r1.status == "RUNNING", f"collect_name status should be RUNNING, got {r1.status}")
    _assert(r1.client_handler.get("command") == "ASK_USER_INPUT", "collect_name must ask for user input")

    r2 = await _agent_request(nc, subject=subject, text="my name is Alice", session_id=session_id)
    _assert(r2.ok is True, "collect_name second call should be ok")
    _assert(r2.status == "DONE", f"collect_name status should be DONE, got {r2.status}")
    _assert(r2.client_handler.get("command") == "SHOW_MESSAGE", "collect_name must show message")
    msg = ((r2.client_handler.get("payload") or {}).get("message") or "")
    _assert("Alice" in str(msg), "collect_name response must include provided name")


async def test_airports_and_weather(nc: NATS, subject: str) -> None:
    session_id = uuid4()

    r1 = await _agent_request(nc, subject=subject, text="airport weather moscow", session_id=session_id)
    _assert(r1.ok is True, "airports first call should be ok (RUNNING)")
    _assert(r1.status == "RUNNING", f"airports status should be RUNNING, got {r1.status}")
    _assert(r1.client_handler.get("command") == "ASK_USER_INPUT", "airports must ask for radius")

    r2 = await _agent_request(nc, subject=subject, text="250", session_id=session_id)
    _assert(r2.ok is True, "airports second call should be ok")
    _assert(r2.status == "DONE", f"airports status should be DONE, got {r2.status}")
    _assert(r2.client_handler.get("command") == "SHOW_AIRPORTS", "airports must return SHOW_AIRPORTS")
    payload = r2.client_handler.get("payload") or {}
    data = payload.get("data") or {}
    _assert(isinstance(data.get("airports"), list), "SHOW_AIRPORTS payload.data.airports must be a list")
    _assert(isinstance(data.get("weather"), dict), "SHOW_AIRPORTS payload.data.weather must be a dict")


async def main() -> None:
    env = _env()

    test_contracts_roundtrip()

    nc = NATS()
    await nc.connect(servers=[env.nats_url], name="src_e2e", max_reconnect_attempts=-1)

    pg = await asyncpg.create_pool(env.database_url, min_size=1, max_size=2)

    try:
        await _wait_for_n8n_bridge(nc, env.n8n_health_subject, timeout_s=90)

        await test_echo_idempotent(nc, pg, env.agent_subject)
        await test_collect_name(nc, env.agent_subject)
        await test_airports_and_weather(nc, env.agent_subject)

        print("E2E OK")
    finally:
        await pg.close()
        await nc.drain()
        await nc.close()


if __name__ == "__main__":
    asyncio.run(main())
