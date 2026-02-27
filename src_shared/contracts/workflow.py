from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from .common import ErrorInfo, TraceEnvelope

WorkflowStatus = Literal["RUNNING", "PARTIAL", "DONE", "FAILED"]


class WorkflowRuntimeState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    active_workflow_id: Optional[str] = None
    pending: Optional[dict[str, Any]] = None
    context: Optional[dict[str, Any]] = None
    version: int = Field(ge=1, default=1)


class WorkflowRunRequest(TraceEnvelope):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1)
    edit: Optional[dict[str, Any]] = None
    runtime: WorkflowRuntimeState = Field(default_factory=WorkflowRuntimeState)


class WorkflowRunResponse(TraceEnvelope):
    model_config = ConfigDict(extra="forbid")

    status: WorkflowStatus
    result: str = ""
    client_handler: dict[str, Any] = Field(default_factory=dict)
    client_events: list[dict[str, Any]] = Field(default_factory=list)
    next_runtime: WorkflowRuntimeState = Field(default_factory=WorkflowRuntimeState)
    errors: list[ErrorInfo] = Field(default_factory=list)

