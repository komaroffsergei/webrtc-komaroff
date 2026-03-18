from __future__ import annotations

import time
from typing import Any, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def now_ts_ms() -> int:
    return int(time.time() * 1000)


class ErrorInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=1)
    message: str = Field(min_length=1)
    details: Optional[dict[str, Any]] = None


class TraceEnvelope(BaseModel):
    """
    Base envelope required on all inter-service payloads.

    Notes:
    - `correlation_id` is optional; if not provided, it should be treated as `trace_id`.
    """

    model_config = ConfigDict(extra="forbid")

    trace_id: UUID
    request_id: UUID
    correlation_id: Optional[UUID] = None
    session_id: Optional[UUID] = None
    ts_ms: int = Field(ge=0)

    @field_validator("ts_ms")
    @classmethod
    def _validate_ts_ms(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("ts_ms must be a positive unix timestamp in milliseconds")
        return v

    @model_validator(mode="after")
    def _default_correlation_id(self) -> "TraceEnvelope":
        if self.correlation_id is None:
            self.correlation_id = self.trace_id
        return self


class ServiceHealthRequest(TraceEnvelope):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["health"] = "health"


class ServiceHealthResponse(TraceEnvelope):
    model_config = ConfigDict(extra="forbid")

    ok: bool
    status: Literal["healthy", "unhealthy"]
    details: dict[str, Any] = Field(default_factory=dict)
    error: Optional[ErrorInfo] = None
