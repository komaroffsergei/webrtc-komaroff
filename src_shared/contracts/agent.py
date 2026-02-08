from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

from .common import ErrorInfo, TraceEnvelope


class AgentInboundRequest(TraceEnvelope):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1)
    edit: Optional[dict[str, Any]] = None
    user_id: Optional[str] = None


class AgentInboundResponse(TraceEnvelope):
    model_config = ConfigDict(extra="forbid")

    ok: bool
    result: Optional[str] = None
    client_handler: Optional[dict[str, Any]] = None
    client_events: list[dict[str, Any]] = Field(default_factory=list)
    status: str
    errors: list[ErrorInfo] = Field(default_factory=list)

