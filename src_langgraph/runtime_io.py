from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from uuid import UUID, uuid4

from nats.aio.client import Client as NATS

from src_shared.contracts import (
    LlmRequest,
    LlmResponse,
    ToolCallRequest,
    ToolCallResponse,
    WorkflowRunRequest,
    now_ts_ms,
)


def _child_trace(parent: WorkflowRunRequest, *, request_id: UUID | None = None) -> dict[str, Any]:
    """Создает trace-блок для дочернего вызова LLM/tool на базе входного запроса."""
    # Preserve trace/correlation across nested LLM/tool calls while generating per-call request_id.
    return {
        "trace_id": parent.trace_id,
        "correlation_id": parent.correlation_id,
        "request_id": request_id or uuid4(),
        "session_id": parent.session_id,
        "ts_ms": now_ts_ms(),
    }


@dataclass(slots=True)
class RuntimeIO:
    """Транспортный слой для request/reply вызовов LLM и tools по NATS."""

    nc: NATS
    llm_subject_prefix: str
    tools_subject_prefix: str
    user_id: str
    request_timeout_s: float = 120.0

    async def call_llm(
        self,
        *,
        parent: WorkflowRunRequest,
        mode: str,
        input_data: dict[str, Any],
        constraints: dict[str, Any] | None = None,
    ) -> LlmResponse:
        """Отправляет запрос в LLM-сервис и валидирует структуру ответа."""
        req = LlmRequest(
            **_child_trace(parent),
            mode=mode,  # type: ignore[arg-type]
            input=input_data,
            constraints=constraints or {},
        )
        raw = await self._request_json(
            f"{self.llm_subject_prefix}{self.user_id}",
            req.model_dump_json().encode("utf-8"),
        )
        return LlmResponse.model_validate(raw)

    async def call_tool(
        self,
        *,
        parent: WorkflowRunRequest,
        tool_name: str,
        args: dict[str, Any],
    ) -> ToolCallResponse:
        """Вызывает tool-сервис по имени инструмента и валидирует ответ."""
        req = ToolCallRequest(
            **_child_trace(parent),
            tool_name=tool_name,
            args=args,
        )
        raw = await self._request_json(
            f"{self.tools_subject_prefix}{tool_name}",
            req.model_dump_json().encode("utf-8"),
        )
        return ToolCallResponse.model_validate(raw)

    async def _request_json(self, subject: str, payload: bytes) -> dict[str, Any]:
        """Базовый request/reply helper: отправляет payload и требует JSON object в ответе."""
        msg = await self.nc.request(subject, payload, timeout=self.request_timeout_s)
        data = json.loads(msg.data.decode("utf-8"))
        if not isinstance(data, dict):
            raise RuntimeError(f"Invalid JSON response from {subject}")
        return data
