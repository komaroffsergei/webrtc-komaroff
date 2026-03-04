from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .common import ErrorInfo, TraceEnvelope


class HistoryTurn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    turn_id: str = Field(min_length=1)
    role: str = Field(min_length=1)
    text: str
    ts_ms: int = Field(ge=0)
    meta: dict[str, Any] = Field(default_factory=dict)


class HistoryGetRequest(TraceEnvelope):
    model_config = ConfigDict(extra="forbid")

    limit: int = Field(ge=1, le=1000, default=200)


class HistoryGetResponse(TraceEnvelope):
    model_config = ConfigDict(extra="forbid")

    ok: bool
    items: list[HistoryTurn] = Field(default_factory=list)
    runtime_context: dict[str, Any] | None = None
    error: ErrorInfo | None = None
