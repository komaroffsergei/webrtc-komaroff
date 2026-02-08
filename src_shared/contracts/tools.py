from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

from .common import ErrorInfo, TraceEnvelope


class ToolCallRequest(TraceEnvelope):
    model_config = ConfigDict(extra="forbid")

    tool_name: str = Field(min_length=1)
    args: dict[str, Any] = Field(default_factory=dict)


class ToolCallResponse(TraceEnvelope):
    model_config = ConfigDict(extra="forbid")

    ok: bool
    artifact_key: Optional[str] = None
    data: Optional[dict[str, Any]] = None
    error: Optional[ErrorInfo] = None

