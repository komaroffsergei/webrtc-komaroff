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
    N8nRunRequest,
    N8nRunResponse,
    N8nRuntimeState,
    now_ts_ms,
)

logger = logging.getLogger("src_agent.runner")


@dataclass(frozen=True)
class RunnerResult:
    session_id: UUID
    n8n: N8nRunResponse


@dataclass
class AgentRunner:
    nc: NATS
    db: Database
    n8n_subject: str
    user_id: str
    n8n_timeout_s: int
    max_runtime_conflict_retries: int = 3
    n8n_no_responders_retries: int = 10
    n8n_no_responders_retry_delay_s: float = 1.0

    async def run(self, req: AgentInboundRequest) -> RunnerResult:
        # Ensure the `sessions` row exists even when the session_id is provided externally.
        session_id = req.session_id or uuid4()
        session_id = UUID(
            await create_session(self.db, user_id=self.user_id, session_id=str(session_id))
        )

        runtime = await load_runtime_state(self.db, session_id=session_id)
        n8n = await self._run_with_optimistic_lock(req=req, session_id=session_id, runtime=runtime)
        return RunnerResult(session_id=session_id, n8n=n8n)

    async def _run_with_optimistic_lock(
        self,
        *,
        req: AgentInboundRequest,
        session_id: UUID,
        runtime: N8nRuntimeState,
    ) -> N8nRunResponse:
        correlation_id = req.correlation_id or req.trace_id

        last_error: Optional[Exception] = None
        for attempt in range(self.max_runtime_conflict_retries + 1):
            inner_request_id = req.request_id if attempt == 0 else uuid4()
            inner_ts_ms = req.ts_ms if attempt == 0 else now_ts_ms()

            n8n_req = N8nRunRequest(
                trace_id=req.trace_id,
                correlation_id=correlation_id,
                request_id=inner_request_id,
                session_id=session_id,
                ts_ms=inner_ts_ms,
                text=req.text,
                edit=req.edit,
                runtime=runtime,
            )

            n8n_resp = await self._call_n8n(n8n_req)

            try:
                await save_runtime_state(
                    self.db,
                    session_id=session_id,
                    expected_version=runtime.version,
                    next_state=n8n_resp.next_runtime,
                )
                return n8n_resp
            except Exception as exc:
                last_error = exc
                if attempt >= self.max_runtime_conflict_retries:
                    break
                runtime = await load_runtime_state(self.db, session_id=session_id)

        logger.exception("runtime_state update failed after retries. session_id=%s", str(session_id))
        return N8nRunResponse(
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

    async def _call_n8n(self, req: N8nRunRequest) -> N8nRunResponse:
        payload = req.model_dump_json().encode("utf-8")
        last_exc: Exception | None = None
        for attempt in range(self.n8n_no_responders_retries + 1):
            try:
                msg = await self.nc.request(self.n8n_subject, payload, timeout=self.n8n_timeout_s)
                break
            except NoRespondersError as exc:
                last_exc = exc
                if attempt >= self.n8n_no_responders_retries:
                    raise
                logger.warning(
                    "No responders for subject=%s (attempt=%s/%s), retrying in %.1fs",
                    self.n8n_subject,
                    attempt + 1,
                    self.n8n_no_responders_retries + 1,
                    self.n8n_no_responders_retry_delay_s,
                )
                await asyncio.sleep(self.n8n_no_responders_retry_delay_s)
        else:
            raise last_exc or RuntimeError("n8n request failed without response")
        raw = json.loads(msg.data.decode("utf-8"))
        return N8nRunResponse.model_validate(raw)
