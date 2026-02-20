from __future__ import annotations

import json
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .common import ErrorInfo, TraceEnvelope

LlmMode = Literal["routing_decision", "params_extract", "revise"]


class LlmRequest(TraceEnvelope):
    model_config = ConfigDict(extra="forbid")

    mode: LlmMode
    input: dict[str, Any]
    constraints: dict[str, Any] = Field(default_factory=dict)


class RoutingDecisionData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workflow_id: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)


class ParamsExtractData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ok: bool = True
    values: dict[str, Any] = Field(default_factory=dict)
    missing: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0, default=0.0)
    notes: list[str] = Field(default_factory=list)


class ReviseData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fixed: Optional[dict[str, Any]] = None
    need_user_input: bool = False
    question: Optional[str] = None

    @model_validator(mode="after")
    def _validate_exclusive(self) -> "ReviseData":
        if self.need_user_input:
            if not (isinstance(self.question, str) and self.question.strip()):
                raise ValueError("question is required when need_user_input=true")
            if self.fixed is not None:
                raise ValueError("fixed must be null when need_user_input=true")
        return self


class LlmResponse(TraceEnvelope):
    model_config = ConfigDict(extra="forbid")

    ok: bool
    data: Optional[dict[str, Any]] = None
    error: Optional[ErrorInfo] = None

    @classmethod
    def from_validated_data(
        cls,
        *,
        request: LlmRequest,
        data: BaseModel,
    ) -> "LlmResponse":
        return cls(
            trace_id=request.trace_id,
            correlation_id=request.correlation_id,
            request_id=request.request_id,
            session_id=request.session_id,
            ts_ms=request.ts_ms,
            ok=True,
            data=json.loads(data.model_dump_json()),
            error=None,
        )
