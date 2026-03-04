from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass
from typing import Any, Optional
from uuid import UUID, uuid4

from nats.aio.client import Client as NATS
from nats.errors import NoRespondersError, TimeoutError as NatsTimeoutError

from src_agent.repositories.runtime_state import load_runtime_state, save_runtime_state
from src_agent.utils.db import Database, chat_turn_exists, create_session, persist_chat_turn
from src_shared.contracts import (
    AgentInboundRequest,
    ErrorInfo,
    WorkflowRunRequest,
    WorkflowRunResponse,
    WorkflowRuntimeState,
    now_ts_ms,
)
from src_shared.contracts.subjects import Subjects

logger = logging.getLogger("src_agent.runner")


@dataclass(frozen=True)
class RunnerResult:
    session_id: UUID
    workflow: WorkflowRunResponse


@dataclass
class AgentRunner:
    nc: NATS
    db: Database
    workflow_subject: str
    user_id: str
    workflow_timeout_s: int
    max_runtime_conflict_retries: int = 3
    workflow_no_responders_retries: int = 4
    workflow_no_responders_retry_delay_s: float = 1.0

    async def run(self, req: AgentInboundRequest) -> RunnerResult:
        # Ensure the `sessions` row exists even when the session_id is provided externally.
        session_id = req.session_id or uuid4()
        session_id = UUID(
            await create_session(self.db, user_id=self.user_id, session_id=str(session_id))
        )

        runtime = await load_runtime_state(self.db, session_id=session_id)
        workflow = await self._run_with_optimistic_lock(req=req, session_id=session_id, runtime=runtime)
        return RunnerResult(session_id=session_id, workflow=workflow)

    async def _run_with_optimistic_lock(
        self,
        *,
        req: AgentInboundRequest,
        session_id: UUID,
        runtime: WorkflowRuntimeState,
    ) -> WorkflowRunResponse:
        correlation_id = req.correlation_id or req.trace_id
        edit_turn_id = self._edit_turn_id(req.edit)
        if edit_turn_id:
            exists = await chat_turn_exists(
                self.db,
                session_id=str(session_id),
                turn_id=edit_turn_id,
            )
            if not exists:
                return WorkflowRunResponse(
                    trace_id=req.trace_id,
                    correlation_id=correlation_id,
                    request_id=req.request_id,
                    session_id=session_id,
                    ts_ms=req.ts_ms,
                    status="FAILED",
                    result="",
                    errors=[ErrorInfo(code="edit_turn_not_found", message="Edited turn was not found in session history.")],
                    next_runtime=runtime,
                )
            # Edits rebuild the branch from the edited user turn, so pending workflow lock must be reset.
            runtime = runtime.model_copy(update={"active_workflow_id": None, "pending": None})
        user_turn_id = edit_turn_id or (req.turn_id.strip() if isinstance(req.turn_id, str) and req.turn_id.strip() else str(uuid4()))

        last_error: Optional[Exception] = None
        for attempt in range(self.max_runtime_conflict_retries + 1):
            inner_request_id = req.request_id if attempt == 0 else uuid4()
            inner_ts_ms = req.ts_ms if attempt == 0 else now_ts_ms()

            workflow_req = WorkflowRunRequest(
                trace_id=req.trace_id,
                correlation_id=correlation_id,
                request_id=inner_request_id,
                session_id=session_id,
                ts_ms=inner_ts_ms,
                text=req.text,
                turn_id=user_turn_id,
                edit=req.edit,
                runtime=runtime,
            )

            workflow_resp = await self._call_workflow(workflow_req)

            try:
                await save_runtime_state(
                    self.db,
                    session_id=session_id,
                    expected_version=runtime.version,
                    next_state=workflow_resp.next_runtime,
                )
                assistant_turn_id = self._assistant_turn_id(workflow_resp) or str(uuid4())
                assistant_text = self._assistant_text(workflow_resp)
                if assistant_text:
                    await persist_chat_turn(
                        self.db,
                        session_id=str(session_id),
                        user_turn_id=user_turn_id,
                        user_text=req.text,
                        assistant_turn_id=assistant_turn_id,
                        assistant_text=assistant_text,
                        edit_from_turn_id=edit_turn_id,
                        user_meta={"request_id": str(req.request_id)},
                        assistant_meta={
                            "request_id": str(workflow_resp.request_id),
                            "status": workflow_resp.status,
                            "user_turn_id": user_turn_id,
                        },
                    )
                return self._inject_turn_ids(workflow_resp, user_turn_id=user_turn_id, assistant_turn_id=assistant_turn_id)
            except ValueError as exc:
                if str(exc) == "edit_turn_not_found":
                    return WorkflowRunResponse(
                        trace_id=req.trace_id,
                        correlation_id=correlation_id,
                        request_id=req.request_id,
                        session_id=session_id,
                        ts_ms=req.ts_ms,
                        status="FAILED",
                        result="",
                        errors=[ErrorInfo(code="edit_turn_not_found", message="Edited turn was not found in session history.")],
                        next_runtime=runtime,
                    )
                last_error = exc
                if attempt >= self.max_runtime_conflict_retries:
                    break
                runtime = await load_runtime_state(self.db, session_id=session_id)
            except Exception as exc:
                last_error = exc
                if attempt >= self.max_runtime_conflict_retries:
                    break
                runtime = await load_runtime_state(self.db, session_id=session_id)

        logger.exception("runtime_state update failed after retries. session_id=%s", str(session_id))
        return WorkflowRunResponse(
            trace_id=req.trace_id,
            correlation_id=correlation_id,
            request_id=req.request_id,
            session_id=session_id,
            ts_ms=req.ts_ms,
            status="FAILED",
            result="",
            errors=[
                ErrorInfo(
                    code="runtime_state_conflict",
                    message="Failed to update runtime state due to concurrent updates.",
                    details={"error": str(last_error)} if last_error else None,
                )
            ],
            next_runtime=runtime,
        )

    async def _call_workflow(self, req: WorkflowRunRequest) -> WorkflowRunResponse:
        payload = req.model_dump_json().encode("utf-8")
        canonical_subject = Subjects.WORKFLOW_RUN
        subjects = [self.workflow_subject]
        if self.workflow_subject != canonical_subject:
            subjects.append(canonical_subject)

        total_attempts = self.workflow_no_responders_retries + 1
        if len(subjects) == 1:
            attempts_by_subject = [total_attempts]
        else:
            first_budget = min(3, max(1, total_attempts - 1))
            attempts_by_subject = [first_budget, total_attempts - first_budget]

        last_exc: Exception | None = None
        for subject, subject_attempts in zip(subjects, attempts_by_subject):
            for attempt in range(subject_attempts):
                try:
                    started_at = time.monotonic()
                    logger.info(
                        "workflow request start subject=%s attempt=%s/%s request_id=%s session_id=%s timeout_s=%s",
                        subject,
                        attempt + 1,
                        subject_attempts,
                        str(req.request_id),
                        str(req.session_id) if req.session_id else "<none>",
                        self.workflow_timeout_s,
                    )
                    msg = await self.nc.request(subject, payload, timeout=self.workflow_timeout_s)
                    duration_ms = int((time.monotonic() - started_at) * 1000)
                    if subject != self.workflow_subject:
                        logger.warning(
                            "Workflow subject switched from %s to %s",
                            self.workflow_subject,
                            subject,
                        )
                        self.workflow_subject = subject
                    raw = json.loads(msg.data.decode("utf-8"))
                    resp = WorkflowRunResponse.model_validate(raw)
                    logger.info(
                        "workflow request done subject=%s request_id=%s status=%s duration_ms=%s",
                        subject,
                        str(req.request_id),
                        resp.status,
                        duration_ms,
                    )
                    return resp
                except NatsTimeoutError as exc:
                    logger.error(
                        "Workflow request timeout subject=%s timeout=%ss request_id=%s session_id=%s",
                        subject,
                        self.workflow_timeout_s,
                        str(req.request_id),
                        str(req.session_id) if req.session_id else "<none>",
                    )
                    return WorkflowRunResponse(
                        trace_id=req.trace_id,
                        correlation_id=req.correlation_id,
                        request_id=req.request_id,
                        session_id=req.session_id,
                        ts_ms=now_ts_ms(),
                        status="FAILED",
                        result="",
                        errors=[
                            ErrorInfo(
                                code="workflow_timeout",
                                message=(
                                    "Сервис сценариев не успел ответить вовремя. "
                                    "Попробуйте повторить запрос."
                                ),
                                details={
                                    "subject": subject,
                                    "timeout_s": self.workflow_timeout_s,
                                },
                            )
                        ],
                        next_runtime=req.runtime,
                    )
                except NoRespondersError as exc:
                    last_exc = exc
                    if attempt >= subject_attempts - 1:
                        break
                    logger.warning(
                        "No responders for subject=%s request_id=%s (attempt=%s/%s), retrying in %.1fs",
                        subject,
                        str(req.request_id),
                        attempt + 1,
                        subject_attempts,
                        self.workflow_no_responders_retry_delay_s,
                    )
                    await asyncio.sleep(self.workflow_no_responders_retry_delay_s)

        waited_s = self.workflow_no_responders_retries * self.workflow_no_responders_retry_delay_s
        subject_list = ", ".join(f"`{s}`" for s in subjects)
        return WorkflowRunResponse(
            trace_id=req.trace_id,
            correlation_id=req.correlation_id,
            request_id=req.request_id,
            session_id=req.session_id,
            ts_ms=now_ts_ms(),
            status="FAILED",
            result="",
            errors=[
                ErrorInfo(
                    code="workflow_unavailable",
                    message=(
                        "Сервис сценариев временно недоступен "
                        f"(нет responder для NATS subject {subject_list} ~{waited_s:.0f}с). "
                        "Повторите запрос через несколько секунд."
                    ),
                    details={"error": str(last_exc)} if last_exc else None,
                )
            ],
            next_runtime=req.runtime,
        )

    @staticmethod
    def _edit_turn_id(edit: Any) -> str | None:
        if not isinstance(edit, dict):
            return None
        value = edit.get("turn_id")
        if not isinstance(value, str):
            return None
        value = value.strip()
        return value or None

    @staticmethod
    def _assistant_text(resp: WorkflowRunResponse) -> str:
        if isinstance(resp.result, str) and resp.result.strip():
            return resp.result.strip()
        if resp.errors and isinstance(resp.errors[0].message, str):
            return resp.errors[0].message.strip()
        return ""

    @staticmethod
    def _assistant_turn_id(resp: WorkflowRunResponse) -> str | None:
        if not isinstance(resp.client_handler, dict):
            return None
        payload = resp.client_handler.get("payload")
        if not isinstance(payload, dict):
            return None
        value = payload.get("assistant_turn_id")
        if not isinstance(value, str):
            return None
        value = value.strip()
        return value or None

    @staticmethod
    def _inject_turn_ids(resp: WorkflowRunResponse, *, user_turn_id: str, assistant_turn_id: str) -> WorkflowRunResponse:
        handler = dict(resp.client_handler or {})
        payload = handler.get("payload") if isinstance(handler.get("payload"), dict) else {}
        payload = dict(payload or {})
        payload.setdefault("user_turn_id", user_turn_id)
        payload.setdefault("assistant_turn_id", assistant_turn_id)
        if handler:
            handler["payload"] = payload
        return resp.model_copy(update={"client_handler": handler})
