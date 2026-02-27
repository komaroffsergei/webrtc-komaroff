from __future__ import annotations

from typing import Any

from src_shared.contracts import (
    ErrorInfo,
    WorkflowRunRequest,
    WorkflowRunResponse,
    WorkflowRuntimeState,
    now_ts_ms,
)


def _base_response_kwargs(req: WorkflowRunRequest) -> dict[str, Any]:
    """Формирует общие trace-поля для любого ответа workflow runtime."""
    return {
        "trace_id": req.trace_id,
        "correlation_id": req.correlation_id,
        "request_id": req.request_id,
        "session_id": req.session_id,
        "ts_ms": now_ts_ms(),
    }


def next_runtime(
    req: WorkflowRunRequest,
    *,
    active_workflow_id: str | None = None,
    pending: dict[str, Any] | None = None,
    context: dict[str, Any] | None = None,
) -> WorkflowRuntimeState:
    """Собирает следующее runtime-состояние с сохранением версии контекста."""
    return WorkflowRuntimeState(
        active_workflow_id=active_workflow_id,
        pending=pending,
        context=context,
        version=req.runtime.version,
    )


def done_response(
    req: WorkflowRunRequest,
    message: str,
    *,
    client_events: list[dict[str, Any]] | None = None,
) -> WorkflowRunResponse:
    """Возвращает успешный финальный ответ и очищает pending-состояние сессии."""
    clean = message.strip() if isinstance(message, str) else ""
    if not clean:
        clean = "Готово."
    return WorkflowRunResponse(
        **_base_response_kwargs(req),
        status="DONE",
        result=clean,
        client_handler={"command": "SHOW_MESSAGE", "payload": {"message": clean}},
        client_events=client_events or [],
        next_runtime=next_runtime(req),
    )


def partial_response(
    req: WorkflowRunRequest,
    prompt: str,
    *,
    active_workflow_id: str,
    pending: dict[str, Any],
) -> WorkflowRunResponse:
    """Возвращает промежуточный ответ с запросом недостающих параметров у пользователя."""
    clean = prompt.strip() if isinstance(prompt, str) else ""
    return WorkflowRunResponse(
        **_base_response_kwargs(req),
        status="PARTIAL",
        result=clean,
        client_handler={"command": "ASK_USER_INPUT", "payload": {"message": clean}},
        next_runtime=next_runtime(req, active_workflow_id=active_workflow_id, pending=pending, context=req.runtime.context),
    )


def failed_response(
    req: WorkflowRunRequest,
    *,
    code: str,
    message: str,
    runtime: WorkflowRuntimeState | None = None,
    client_handler: dict[str, Any] | None = None,
) -> WorkflowRunResponse:
    """Возвращает ошибку выполнения сценария без падения обработчика NATS."""
    return WorkflowRunResponse(
        **_base_response_kwargs(req),
        status="FAILED",
        result="",
        client_handler=client_handler or {},
        next_runtime=runtime or next_runtime(req),
        errors=[ErrorInfo(code=code, message=message)],
    )
