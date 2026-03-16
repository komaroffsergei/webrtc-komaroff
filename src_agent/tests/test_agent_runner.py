from __future__ import annotations

import json
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import Mock
from uuid import uuid4

from nats.errors import NoRespondersError

from src_agent.agent import AgentRunner
from src_shared.contracts import WorkflowRunRequest, WorkflowRuntimeState, now_ts_ms
from src_shared.contracts.subjects import Subjects


class FakeNatsClient:
    def __init__(self, outcomes: list[Exception | dict]) -> None:
        self._outcomes = list(outcomes)
        self.calls: list[tuple[str, float]] = []

    async def request(self, subject: str, payload: bytes, timeout: float):
        self.calls.append((subject, timeout))
        outcome = self._outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return SimpleNamespace(data=json.dumps(outcome).encode("utf-8"))


class AgentRunnerWorkflowSubjectTests(IsolatedAsyncioTestCase):
    workflow_subject = "nats.workflow.run.ruby"

    def _runner(self, outcomes: list[Exception | dict], retries: int = 4) -> tuple[AgentRunner, FakeNatsClient]:
        nc = FakeNatsClient(outcomes)
        runner = AgentRunner(
            nc=nc,
            db=Mock(),
            workflow_subject=self.workflow_subject,
            user_id="user123",
            workflow_timeout_s=15,
            workflow_no_responders_retries=retries,
            workflow_no_responders_retry_delay_s=0.0,
        )
        return runner, nc

    @staticmethod
    def _request() -> WorkflowRunRequest:
        return WorkflowRunRequest(
            trace_id=uuid4(),
            correlation_id=None,
            request_id=uuid4(),
            session_id=uuid4(),
            ts_ms=now_ts_ms(),
            text="как дела",
            runtime=WorkflowRuntimeState(),
        )

    def _response_payload(self, req: WorkflowRunRequest) -> dict:
        return {
            "trace_id": str(req.trace_id),
            "correlation_id": str(req.correlation_id),
            "request_id": str(req.request_id),
            "session_id": str(req.session_id),
            "ts_ms": now_ts_ms(),
            "status": "DONE",
            "result": "ok",
            "client_handler": {"command": "SHOW_MESSAGE", "payload": {"message": "ok"}},
            "client_events": [],
            "errors": [],
            "next_runtime": req.runtime.model_dump(),
        }

    async def test_no_responders_retries_only_configured_subject(self) -> None:
        runner, nc = self._runner([NoRespondersError() for _ in range(5)], retries=4)

        response = await runner._call_workflow(self._request())

        self.assertEqual(response.status, "FAILED")
        self.assertEqual(response.errors[0].code, "workflow_unavailable")
        self.assertEqual(response.errors[0].details["subject"], self.workflow_subject)
        self.assertEqual([subject for subject, _ in nc.calls], [self.workflow_subject] * 5)
        self.assertNotIn(Subjects.WORKFLOW_RUN, [subject for subject, _ in nc.calls if subject != self.workflow_subject])

    async def test_success_after_retry_keeps_configured_subject(self) -> None:
        req = self._request()
        runner, nc = self._runner(
            [
                NoRespondersError(),
                NoRespondersError(),
                self._response_payload(req),
            ],
            retries=4,
        )

        response = await runner._call_workflow(req)

        self.assertEqual(response.status, "DONE")
        self.assertEqual(response.result, "ok")
        self.assertEqual([subject for subject, _ in nc.calls], [self.workflow_subject] * 3)
