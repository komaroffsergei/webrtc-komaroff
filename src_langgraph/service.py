from __future__ import annotations

import asyncio
import json
import logging
import signal
from typing import Any
from uuid import uuid4

import nats
from nats.aio.client import Client as NATS
from nats.aio.msg import Msg

from src_langgraph.engine import WorkflowEngine
from src_langgraph.responses import failed_response
from src_langgraph.runtime_io import RuntimeIO
from src_shared.contracts import (
    ErrorInfo,
    ServiceHealthRequest,
    ServiceHealthResponse,
    WorkflowRunRequest,
    WorkflowRunResponse,
    now_ts_ms,
)

logger = logging.getLogger("src_langgraph")


class WorkflowRuntimeService:
    """NATS-сервис исполнения сценариев: run/health подписки и обработка запросов."""

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
        memory_recent_messages: int = 32,
        memory_summary_max_chars: int = 12000,
        memory_context_max_chars: int = 18000,
    ) -> None:
        """Сохраняет настройки подключения и лимиты конкурентности обработки."""
        self.nats_url = nats_url
        self.run_subject = run_subject
        self.health_subject = health_subject
        self._io_cfg = {
            "llm_subject_prefix": llm_subject_prefix,
            "tools_subject_prefix": tools_subject_prefix,
            "user_id": user_id,
            "request_timeout_s": request_timeout_s,
        }
        self._stop = asyncio.Event()
        self._tasks: set[asyncio.Task[Any]] = set()
        self._semaphore = asyncio.Semaphore(max(1, int(max_concurrency)))
        self._nc: NATS | None = None
        self._engine: WorkflowEngine | None = None
        self._memory_cfg = {
            "memory_recent_messages": int(memory_recent_messages),
            "memory_summary_max_chars": int(memory_summary_max_chars),
            "memory_context_max_chars": int(memory_context_max_chars),
        }

    async def run(self) -> None:
        """Подключается к NATS, регистрирует подписки и ждет сигнала остановки."""
        self._nc = await nats.connect(
            servers=[self.nats_url],
            name="src_langgraph",
            max_reconnect_attempts=-1,
            reconnect_time_wait=2,
            ping_interval=10,
        )
        io = RuntimeIO(nc=self._nc, **self._io_cfg)
        self._engine = WorkflowEngine(io, **self._memory_cfg)

        await self._nc.subscribe(self.run_subject, queue="src_langgraph.run.q", cb=self._handle_run)
        await self._nc.subscribe(self.health_subject, queue="src_langgraph.health.q", cb=self._handle_health)
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
        await self._nc.drain()
        await self._nc.close()
        self._nc = None
        self._engine = None

    async def shutdown(self, signal_obj=None) -> None:
        """Запрашивает корректное завершение основного цикла сервиса."""
        logger.info("Shutdown requested: %s", getattr(signal_obj, "name", signal_obj))
        self._stop.set()

    async def _handle_run(self, msg: Msg) -> None:
        """Создает отдельную async-задачу для каждого входящего run-сообщения."""
        task = asyncio.create_task(self._process_run_message(msg))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _process_run_message(self, msg: Msg) -> None:
        """Валидирует run-запрос, запускает движок и отправляет ответ в reply-subject."""
        # Bound concurrent workflow executions to protect LLM/tools and avoid event loop overload.
        async with self._semaphore:
            try:
                req = WorkflowRunRequest.model_validate(json.loads(msg.data.decode("utf-8")))
            except Exception as exc:
                resp = WorkflowRunResponse(
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

            # Runtime state is keyed by session_id; requests without session cannot be processed safely.
            if req.session_id is None:
                resp = failed_response(req, code="missing_session_id", message="session_id is required", runtime=req.runtime)
                await self._safe_respond(msg, resp.model_dump_json().encode("utf-8"))
                return

            try:
                if self._engine is None:
                    raise RuntimeError("workflow engine is not initialized")
                resp = await self._engine.run(req)
            except Exception as exc:
                logger.exception("Workflow execution failed")
                resp = failed_response(req, code="workflow_failed", message=str(exc), runtime=req.runtime)

            await self._safe_respond(msg, resp.model_dump_json().encode("utf-8"))

    async def _handle_health(self, msg: Msg) -> None:
        """Обрабатывает health-check и возвращает состояние runtime-сервиса."""
        try:
            req = ServiceHealthRequest.model_validate(json.loads(msg.data.decode("utf-8")))
            resp = ServiceHealthResponse(
                trace_id=req.trace_id,
                correlation_id=req.correlation_id,
                request_id=req.request_id,
                session_id=req.session_id,
                ts_ms=now_ts_ms(),
                ok=self._nc is not None and self._engine is not None,
                status="healthy" if self._nc is not None and self._engine is not None else "unhealthy",
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

    @staticmethod
    async def _safe_respond(msg: Msg, payload: bytes) -> None:
        """Отправляет ответ только если reply-subject присутствует, с защитой от исключений."""
        if not msg.reply:
            return
        try:
            await msg.respond(payload)
        except Exception:
            logger.exception("Failed to respond on NATS")
