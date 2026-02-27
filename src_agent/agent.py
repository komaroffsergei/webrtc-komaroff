from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from typing import Any, Optional
from uuid import UUID, uuid4

from nats.aio.client import Client as NATS
from nats.errors import NoRespondersError

from src_agent.repositories.runtime_state import load_runtime_state, save_runtime_state
from src_agent.utils.db import Database, create_session
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
    # During deploys workflow responder can be temporarily unavailable.
    # Keep retrying long enough to survive the rollout window.
    workflow_no_responders_retries: int = 60
    workflow_no_responders_retry_delay_s: float = 2.0

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
                return workflow_resp
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
                    msg = await self.nc.request(subject, payload, timeout=self.workflow_timeout_s)
                    if subject != self.workflow_subject:
                        logger.warning(
                            "Workflow subject switched from %s to %s",
                            self.workflow_subject,
                            subject,
                        )
                        self.workflow_subject = subject
                    raw = json.loads(msg.data.decode("utf-8"))
                    return WorkflowRunResponse.model_validate(raw)
                except NoRespondersError as exc:
                    last_exc = exc
                    if attempt >= subject_attempts - 1:
                        break
                    logger.warning(
                        "No responders for subject=%s (attempt=%s/%s), retrying in %.1fs",
                        subject,
                        attempt + 1,
                        subject_attempts,
                        self.workflow_no_responders_retry_delay_s,
                    )
                    await asyncio.sleep(self.workflow_no_responders_retry_delay_s)

        waited_s = self.workflow_no_responders_retries * self.workflow_no_responders_retry_delay_s
        subject_list = ", ".join(f"`{s}`" for s in subjects)
        raise RuntimeError(
            "Сервис сценариев временно недоступен "
            f"(нет responder для NATS subject {subject_list} ~{waited_s:.0f}с). "
            "Вероятно, workflow-service еще запускается. Повторите запрос через несколько секунд."
        ) from last_exc
