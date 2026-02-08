from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from .common import ErrorInfo, TraceEnvelope

N8nStatus = Literal["RUNNING", "DONE", "FAILED"]


class N8nRuntimeState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    active_workflow_id: Optional[str] = None
    pending: Optional[dict[str, Any]] = None
    context: Optional[dict[str, Any]] = None
    version: int = Field(ge=1, default=1)


class N8nRunRequest(TraceEnvelope):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1)
    edit: Optional[dict[str, Any]] = None
    runtime: N8nRuntimeState = Field(default_factory=N8nRuntimeState)


class N8nRunResponse(TraceEnvelope):
    model_config = ConfigDict(extra="forbid")

    status: N8nStatus
    result: str = ""
    client_handler: dict[str, Any] = Field(default_factory=dict)
    client_events: list[dict[str, Any]] = Field(default_factory=list)
    next_runtime: N8nRuntimeState = Field(default_factory=N8nRuntimeState)
    errors: list[ErrorInfo] = Field(default_factory=list)

