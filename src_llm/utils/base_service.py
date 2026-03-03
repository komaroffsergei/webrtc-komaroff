import asyncio
import json
import logging
import signal
import time
from typing import Any

import nats
from nats.aio.msg import Msg

from src_llm.settings import STACK_SERVICE_NAME
from src_llm.utils.nats_logger import NatsLogger
from src_llm.utils.nats_publisher import NatsPublisher

logger = logging.getLogger(f"{STACK_SERVICE_NAME}(BaseService)")


class BaseService:
    def __init__(
            self,
            *,
            service_name: str,
            nats_url: str,
            llm_subject: str,
            events_subject: str,
            max_concurrency: int = 1,

    ) -> None:
        self._service_name = service_name
        self._nats_url = nats_url
        self._llm_subject = llm_subject
        self._events_subject = events_subject
        self._nc: nats.NATS
        self._nats_logger: NatsLogger
        self._stop_event = asyncio.Event()
        self._tasks: set[asyncio.Task] = set()
        self._semaphore = asyncio.Semaphore(max(1, max_concurrency))
    def _register_signals(self) -> None:
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, self.stop)
            except NotImplementedError:
                logger.debug("Signal handlers are not supported on this platform")

    async def _connect(self) -> None:
        logger.info("Connecting to NATS: service=%s url=%s", self._service_name, self._nats_url)
        self._nc = await nats.connect(
            servers=[self._nats_url],
            name=self._service_name,
            max_reconnect_attempts=-1,
            reconnect_time_wait=2,
            ping_interval=10,
        )
        self._publisher = NatsPublisher(self._nc)
        self._nats_logger = NatsLogger(self._nc, self._events_subject, self._service_name)
        await self._nats_logger.info(f"{STACK_SERVICE_NAME} service connected")

        # Queue group prevents duplicate processing if multiple llm instances are running.
        await self._nc.subscribe(self._llm_subject, queue=f"{self._service_name}.q", cb=self._handle_message)
        await self._nats_logger.info(f"Subscribed to {self._llm_subject}")
        logger.info("Subscribed to subject=%s queue=%s.q", self._llm_subject, self._service_name)

    async def run(self) -> None:
        await self._connect()
        self._register_signals()
        await self.on_run()
        await self._stop_event.wait()
        await self._shutdown()

    async def _shutdown(self) -> None:
        for task in list(self._tasks):
            task.cancel()

        if self._nc:
            try:
                await self._nc.drain()
            except Exception:
                await self._nc.close()

    def stop(self) -> None:
        self._stop_event.set()

    async def _handle_message(self, msg: Msg) -> None:
        task = asyncio.create_task(self._process_message(msg))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _process_message(self, msg: Msg) -> None:
        if not self._nats_logger:
            return

        req_mode: str | None = None
        raw_req: dict[str, Any] | None = None
        try:
            parsed = json.loads(msg.data.decode("utf-8"))
            if isinstance(parsed, dict):
                raw_req = parsed
            if isinstance(raw_req, dict) and isinstance(raw_req.get("mode"), str):
                req_mode = raw_req["mode"].strip()
        except Exception:
            req_mode = None
            raw_req = None

        if raw_req is not None:
            req_debug = self._llm_request_debug(raw_req)
            extra = self._request_debug_extra(raw_req)
            if isinstance(extra, dict) and extra:
                req_debug["runtime"] = extra
            await self._nats_logger.info(req_debug, name="llm_request_debug")

        duration_ms = 0
        request_id = ""
        if isinstance(raw_req, dict):
            request_id = str(raw_req.get("request_id") or "").strip()
        logger.info(
            "LLM request start request_id=%s mode=%s",
            request_id or "<unknown>",
            req_mode or "<unknown>",
        )
        async with self._semaphore:
            try:
                started_at = time.monotonic()
                text = await asyncio.to_thread(self.on_message, msg)
                duration_ms = int((time.monotonic() - started_at) * 1000)
            except Exception as exc:
                logger.exception("Process message error: %s", exc)
                await self._nats_logger.error(f"Process message error: {exc}")
                await self._reply(
                    msg,
                    {"error": "process_message", "details": str(exc)},
                )
                return

        logger.info(
            "LLM request done request_id=%s mode=%s duration_ms=%s",
            request_id or "<unknown>",
            req_mode or "<unknown>",
            duration_ms,
        )

        await self._nats_logger.info(
            self._llm_result_debug(
                text,
                req_mode=req_mode,
                raw_req=raw_req,
                duration_ms=duration_ms,
            ),
            name="llm_result",
        )
        thought = self._routing_thought_from_llm_result(text, req_mode=req_mode)
        if thought:
            await self._nats_logger.log("command", "thought", thought)
        await self._reply(msg, text)


    async def _reply(self, msg: Msg, payload: dict[str, Any]) -> None:
        if not msg.reply or not self._nc:
            return
        await self._publisher.publish(msg.reply, payload)

    @classmethod
    def _llm_request_debug(cls, raw_req: dict[str, Any]) -> dict[str, Any]:
        constraints = raw_req.get("constraints") if isinstance(raw_req.get("constraints"), dict) else {}
        requested_model = constraints.get("model")
        trace = {
            "trace_id": raw_req.get("trace_id"),
            "correlation_id": raw_req.get("correlation_id"),
            "request_id": raw_req.get("request_id"),
            "session_id": raw_req.get("session_id"),
            "ts_ms": raw_req.get("ts_ms"),
        }
        return {
            "trace": trace,
            "mode": raw_req.get("mode"),
            "requested_model": requested_model if isinstance(requested_model, str) and requested_model.strip() else None,
            "constraints": cls._truncate_debug_value(constraints, depth=0),
            "input": cls._truncate_debug_value(raw_req.get("input"), depth=0),
        }

    def _request_debug_extra(self, raw_req: dict[str, Any]) -> dict[str, Any]:
        return {}

    def _llm_result_debug(
        self,
        payload: Any,
        *,
        req_mode: str | None,
        raw_req: dict[str, Any] | None,
        duration_ms: int,
    ) -> Any:
        return payload

    @classmethod
    def _truncate_debug_value(cls, value: Any, *, depth: int) -> Any:
        if depth >= 5:
            return "<max_depth_reached>"
        if isinstance(value, str):
            return value if len(value) <= 700 else f"{value[:680]}...<truncated>"
        if isinstance(value, list):
            clipped = [cls._truncate_debug_value(v, depth=depth + 1) for v in value[:20]]
            if len(value) > 20:
                clipped.append(f"<truncated_items:{len(value) - 20}>")
            return clipped
        if isinstance(value, dict):
            out: dict[str, Any] = {}
            for i, (k, v) in enumerate(value.items()):
                if i >= 30:
                    out["<truncated_keys>"] = len(value) - 30
                    break
                out[str(k)] = cls._truncate_debug_value(v, depth=depth + 1)
            return out
        return value

    @staticmethod
    def _routing_thought_from_llm_result(payload: Any, *, req_mode: str | None) -> dict[str, Any] | None:
        if req_mode != "routing_decision":
            return None
        if not isinstance(payload, dict):
            return None
        if payload.get("ok") is not True:
            return None

        data = payload.get("data")
        if not isinstance(data, dict):
            return None

        workflow_id = data.get("workflow_id")
        reason = data.get("reason")
        confidence = data.get("confidence")
        if not isinstance(workflow_id, str) or not workflow_id.strip():
            return None
        if not isinstance(reason, str) or not reason.strip():
            return None

        trace = {
            "trace_id": str(payload.get("trace_id") or ""),
            "correlation_id": str(payload.get("correlation_id") or payload.get("trace_id") or ""),
            "request_id": str(payload.get("request_id") or ""),
            "session_id": str(payload.get("session_id")) if payload.get("session_id") else None,
        }

        thought: dict[str, Any] = {
            "summary": "Thinking…",
            "content": reason.strip(),
            "scenario": {"id": workflow_id.strip()},
            "trace": trace,
        }
        if isinstance(confidence, (int, float)):
            thought["confidence"] = float(confidence)
        return thought

    def on_message(self, msg: Msg) -> Any:
        raise NotImplementedError

    async def on_run(self) -> None:
        raise NotImplementedError
