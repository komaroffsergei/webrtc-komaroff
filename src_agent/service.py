from __future__ import annotations

import asyncio
import json
import logging
import signal
import sys
from uuid import uuid4

from nats.aio.client import Client as NATS
from nats.aio.msg import Msg

from src_agent.agent import AgentRunner
from src_agent.repositories.runtime_state import load_runtime_context
from src_agent.settings import STACK_SERVICE_NAME
from src_agent.ui_events import UiEventPublisher
from src_agent.utils.db import Database, fetch_chat_history
from src_agent.utils.nats_logger import NatsLogger
from src_shared.contracts import (
    AgentInboundRequest,
    AgentInboundResponse,
    ErrorInfo,
    HistoryGetRequest,
    HistoryGetResponse,
    now_ts_ms,
)

logger = logging.getLogger(STACK_SERVICE_NAME)


class AgentServer:
    """
    Thin NATS runner:
    - validates inbound requests
    - ensures DB session/runtime rows
    - calls workflow runtime via NATS
    - persists updated runtime state
    - publishes UI commands/events
    """

    def __init__(
        self,
        *,
        nats_url: str,
        agent_subject: str,
        agent_history_subject: str,
        events_subject: str,
        workflow_subject: str,
        workflow_timeout_s: int,
        workflow_no_responders_retries: int,
        workflow_no_responders_retry_delay_s: float,
        db_url: str,
        user_id: str,
        runtime_conflict_retries: int,
    ) -> None:
        self.nats_url = nats_url
        self.agent_subject = agent_subject
        self.agent_history_subject = agent_history_subject
        self.events_subject = events_subject
        self.workflow_subject = workflow_subject
        self.workflow_timeout_s = int(workflow_timeout_s)
        self.workflow_no_responders_retries = max(0, int(workflow_no_responders_retries))
        self.workflow_no_responders_retry_delay_s = max(0.1, float(workflow_no_responders_retry_delay_s))
        self.runtime_conflict_retries = int(runtime_conflict_retries)
        self.db_url = db_url
        self.user_id = user_id

        self.nc: NATS | None = None
        self.db: Database | None = None
        self.nats_logger: NatsLogger | None = None
        self.runner: AgentRunner | None = None
        self.ui_publisher: UiEventPublisher | None = None
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
        self.ui_publisher = UiEventPublisher(self.nats_logger)

        self.db = Database(db_url=self.db_url)
        await self.db.connect()
        self.runner = AgentRunner(
            nc=self.nc,
            db=self.db,
            workflow_subject=self.workflow_subject,
            user_id=self.user_id,
            workflow_timeout_s=self.workflow_timeout_s,
            max_runtime_conflict_retries=self.runtime_conflict_retries,
            workflow_no_responders_retries=self.workflow_no_responders_retries,
            workflow_no_responders_retry_delay_s=self.workflow_no_responders_retry_delay_s,
        )
        await self.nats_logger.info(f"{STACK_SERVICE_NAME} connected (nats={self.nats_url})")

    async def subscribe(self) -> None:
        if not self.nc:
            raise RuntimeError("NATS is not connected")
        await self.nc.subscribe(
            self.agent_subject,
            queue=f"{STACK_SERVICE_NAME}.q.{self.user_id}",
            cb=self.handle_request,
        )
        await self.nc.subscribe(
            self.agent_history_subject,
            queue=f"{STACK_SERVICE_NAME}.history.q.{self.user_id}",
            cb=self.handle_history_request,
        )
        if self.nats_logger:
            await self.nats_logger.info(f"Subscribed to {self.agent_subject} and {self.agent_history_subject}")

    async def handle_request(self, msg: Msg) -> None:
        try:
            raw = json.loads(msg.data.decode("utf-8"))
            if isinstance(raw, dict) and isinstance(raw.get("text"), str):
                raw["text"] = raw["text"].strip()
            req = AgentInboundRequest.model_validate(raw)

            if not self.runner:
                raise RuntimeError("AgentServer is not initialized")

            rr = await self.runner.run(req)
            if self.ui_publisher:
                await self.ui_publisher.publish(req, rr.workflow)

            resp = AgentInboundResponse(
                trace_id=req.trace_id,
                correlation_id=req.correlation_id,
                request_id=req.request_id,
                session_id=rr.session_id,
                ts_ms=now_ts_ms(),
                ok=rr.workflow.status != "FAILED",
                status=rr.workflow.status,
                result=rr.workflow.result,
                client_handler=rr.workflow.client_handler,
                client_events=rr.workflow.client_events,
                errors=rr.workflow.errors,
            )
            await msg.respond(resp.model_dump_json().encode("utf-8"))

        except Exception as exc:
            logger.exception("Error processing request")
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
                errors=[ErrorInfo(code="agent_exception", message=str(exc))],
            )
            try:
                await msg.respond(fallback.model_dump_json().encode("utf-8"))
            except Exception:
                logger.exception("Failed to respond with error")
            if self.nats_logger:
                await self.nats_logger.error(f"Processing error: {str(exc)}")

    async def handle_history_request(self, msg: Msg) -> None:
        try:
            raw = json.loads(msg.data.decode("utf-8"))
            req = HistoryGetRequest.model_validate(raw)
            if req.session_id is None:
                raise ValueError("session_id is required")
            if self.db is None:
                raise RuntimeError("AgentServer DB is not initialized")

            items = await fetch_chat_history(
                self.db,
                session_id=str(req.session_id),
                limit=req.limit,
            )
            runtime_context = await load_runtime_context(
                self.db,
                session_id=req.session_id,
            )
            resp = HistoryGetResponse(
                trace_id=req.trace_id,
                correlation_id=req.correlation_id,
                request_id=req.request_id,
                session_id=req.session_id,
                ts_ms=now_ts_ms(),
                ok=True,
                items=items,
                runtime_context=runtime_context,
                error=None,
            )
            await msg.respond(resp.model_dump_json().encode("utf-8"))
        except Exception as exc:
            logger.exception("Error processing history request")
            fallback = HistoryGetResponse(
                trace_id=uuid4(),
                correlation_id=None,
                request_id=uuid4(),
                session_id=None,
                ts_ms=now_ts_ms(),
                ok=False,
                items=[],
                runtime_context=None,
                error=ErrorInfo(code="history_exception", message=str(exc)),
            )
            try:
                await msg.respond(fallback.model_dump_json().encode("utf-8"))
            except Exception:
                logger.exception("Failed to respond with history error")

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
