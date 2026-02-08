from __future__ import annotations

import asyncio
import json
import logging
import signal
import sys
from hashlib import sha256
from typing import Any
from uuid import uuid4

from nats.aio.client import Client as NATS
from nats.aio.msg import Msg

from src_agent.agent import AgentRunner
from src_agent.settings import STACK_SERVICE_NAME
from src_agent.utils.db import Database
from src_agent.utils.nats_logger import NatsLogger
from src_shared.contracts import (
    AgentInboundRequest,
    AgentInboundResponse,
    ErrorInfo,
    N8nRunResponse,
    now_ts_ms,
)

logger = logging.getLogger(STACK_SERVICE_NAME)


class AgentServer:
    """
    Thin NATS runner:
    - validates inbound requests
    - ensures a DB session/runtime_state row
    - calls n8n via NATS bridge (req-reply)
    - persists next runtime state (optimistic lock)
    - publishes UI commands/events over NATS
    """

    def __init__(
        self,
        *,
        nats_url: str,
        agent_subject: str,
        events_subject: str,
        n8n_subject: str,
        n8n_timeout_s: int,
        db_url: str,
        user_id: str,
        runtime_conflict_retries: int,
    ) -> None:
        self.nats_url = nats_url
        self.agent_subject = agent_subject
        self.events_subject = events_subject
        self.n8n_subject = n8n_subject
        self.n8n_timeout_s = int(n8n_timeout_s)
        self.runtime_conflict_retries = int(runtime_conflict_retries)

        self.db_url = db_url
        self.user_id = user_id

        self.nc: NATS | None = None
        self.db: Database | None = None
        self.nats_logger: NatsLogger | None = None
        self.runner: AgentRunner | None = None

        self.stop_event = asyncio.Event()

    async def connect(self) -> None:
        self.nc = NATS()
        await self.nc.connect(
            servers=[self.nats_url],
            name=STACK_SERVICE_NAME,
            max_reconnect_attempts=-1,
            reconnect_time_wait=2,
            ping_interval=10,
        )

        self.nats_logger = NatsLogger(self.nc, self.events_subject, STACK_SERVICE_NAME)

        self.db = Database(db_url=self.db_url)
        await self.db.connect()

        self.runner = AgentRunner(
            nc=self.nc,
            db=self.db,
            n8n_subject=self.n8n_subject,
            user_id=self.user_id,
            n8n_timeout_s=self.n8n_timeout_s,
            max_runtime_conflict_retries=self.runtime_conflict_retries,
        )

        await self.nats_logger.info(f"{STACK_SERVICE_NAME} connected (nats={self.nats_url})")

    async def subscribe(self) -> None:
        if not self.nc:
            raise RuntimeError("NATS is not connected")
        # Queue group prevents duplicate processing if multiple agent instances are running.
        await self.nc.subscribe(
            self.agent_subject,
            queue=f"{STACK_SERVICE_NAME}.q.{self.user_id}",
            cb=self.handle_request,
        )
        if self.nats_logger:
            await self.nats_logger.info(f"Subscribed to {self.agent_subject}")

    async def handle_request(self, msg: Msg) -> None:
        try:
            raw = json.loads(msg.data.decode("utf-8"))
            if isinstance(raw, dict) and isinstance(raw.get("text"), str):
                raw["text"] = raw["text"].strip()
            req = AgentInboundRequest.model_validate(raw)
            if not self.runner or not self.nats_logger:
                raise RuntimeError("AgentServer is not initialized")

            rr = await self.runner.run(req)
            await self._publish_ui_events(req, rr.n8n)

            resp = AgentInboundResponse(
                trace_id=req.trace_id,
                correlation_id=req.correlation_id,
                request_id=req.request_id,
                session_id=rr.session_id,
                ts_ms=now_ts_ms(),
                ok=rr.n8n.status != "FAILED",
                status=rr.n8n.status,
                result=rr.n8n.result,
                client_handler=rr.n8n.client_handler,
                client_events=rr.n8n.client_events,
                errors=rr.n8n.errors,
            )
            await msg.respond(resp.model_dump_json().encode("utf-8"))

        except Exception as exc:
            logger.exception("Error processing request")
            err = ErrorInfo(code="agent_exception", message=str(exc))
            fallback = AgentInboundResponse(
                trace_id=uuid4(),
                correlation_id=None,
                request_id=uuid4(),
                session_id=None,
                ts_ms=now_ts_ms(),
                ok=False,
                status="FAILED",
                result="",
                client_handler={},
                client_events=[],
                errors=[err],
            )
            try:
                await msg.respond(fallback.model_dump_json().encode("utf-8"))
            except Exception:
                logger.exception("Failed to respond with error")
            if self.nats_logger:
                await self.nats_logger.error(f"Processing error: {str(exc)}")

    def setup_signal_handlers(self) -> None:
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, lambda s=sig: asyncio.create_task(self.shutdown(s)))

    async def shutdown(self, signal_obj=None) -> None:
        if signal_obj:
            logger.info("Received exit signal %s", getattr(signal_obj, "name", signal_obj))
        self.stop_event.set()

        if self.nc:
            try:
                await self.nc.drain()
            except Exception:
                logger.exception("Error draining NATS connection")
            finally:
                await self.nc.close()
                logger.info("NATS connection closed")

        if self.db:
            try:
                await self.db.close()
            except Exception:
                logger.exception("Error closing DB pool")

    async def run(self) -> None:
        try:
            await self.connect()
            await self.subscribe()
            self.setup_signal_handlers()
            logger.info("%s is ready", STACK_SERVICE_NAME)
            await self.stop_event.wait()
        except Exception as exc:
            logger.exception("Server error: %s", str(exc))
            sys.exit(1)
        finally:
            await self.shutdown()

    async def _publish_ui_events(self, req: AgentInboundRequest, resp: N8nRunResponse) -> None:
        if not self.nats_logger:
            return

        trace = {
            "trace_id": str(req.trace_id),
            "correlation_id": str(req.correlation_id or req.trace_id),
            "request_id": str(req.request_id),
            "session_id": str(resp.session_id) if resp.session_id else None,
        }

        msg_text = _extract_result_message(resp)
        if msg_text:
            await self.nats_logger.log(
                "command",
                "message",
                {
                    "type": "answer" if resp.status != "FAILED" else "system",
                    "text": msg_text,
                    "trace": trace,
                },
            )

        sent: set[str] = set()
        for ev in _normalize_client_events(resp.client_events):
            await self._publish_client_command(ev, trace, sent)

        if resp.client_handler:
            await self._publish_client_command(resp.client_handler, trace, sent)

        if resp.status == "FAILED" and resp.errors and not _has_explicit_error_command(resp):
            await self._publish_client_command(
                {
                    "command": "SHOW_ERROR_MESSAGE",
                    "payload": {"message": resp.errors[0].message, "code": resp.errors[0].code},
                },
                trace,
                sent,
            )

    async def _publish_client_command(
        self,
        handler: dict[str, Any],
        trace: dict[str, Any],
        sent: set[str],
    ) -> None:
        if not self.nats_logger:
            return

        fp = _fingerprint_client_command(handler)
        if fp in sent:
            return
        sent.add(fp)

        command = handler.get("command")
        if not isinstance(command, str) or not command.strip():
            return

        artifacts = _payload_to_artifacts(handler.get("payload"))
        data: dict[str, Any] = {"command": command.strip(), "trace": trace}
        if artifacts:
            data["artifacts"] = artifacts

        await self.nats_logger.log("command", "client", data)


def _extract_result_message(resp: N8nRunResponse) -> str | None:
    if isinstance(resp.result, str) and resp.result.strip():
        return resp.result.strip()
    if resp.errors:
        first = resp.errors[0]
        if isinstance(first.message, str) and first.message.strip():
            return first.message.strip()
    return None


def _normalize_client_events(events: Any) -> list[dict[str, Any]]:
    if not isinstance(events, list):
        return []
    return [e for e in events if isinstance(e, dict)]


def _has_explicit_error_command(resp: N8nRunResponse) -> bool:
    def _is_error_cmd(cmd: Any) -> bool:
        if not isinstance(cmd, str):
            return False
        c = cmd.strip().upper()
        return c.startswith("SHOW_ERROR")

    if resp.client_handler and _is_error_cmd(resp.client_handler.get("command")):
        return True
    for ev in _normalize_client_events(resp.client_events):
        if _is_error_cmd(ev.get("command")):
            return True
    return False


def _fingerprint_client_command(handler: dict[str, Any]) -> str:
    try:
        raw = json.dumps(handler, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
    except Exception:
        raw = repr(handler)
    return sha256(raw.encode("utf-8")).hexdigest()


def _payload_to_artifacts(payload: Any) -> dict[str, Any] | None:
    if not isinstance(payload, dict) or not payload:
        return None
    key = "ui"
    return {"all": [key], "last": key, "payload": {key: payload}}
