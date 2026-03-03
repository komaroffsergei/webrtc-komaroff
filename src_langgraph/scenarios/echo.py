from __future__ import annotations

from src_shared.contracts import WorkflowRunRequest, WorkflowRunResponse

from src_langgraph.responses import done_response
from src_langgraph.router import parse_echo_payload


async def run_echo(req: WorkflowRunRequest) -> WorkflowRunResponse:
    """Возвращает пользователю его же текст (с удалением префикса echo/эхо)."""
    text = parse_echo_payload(req.text)
    if not text:
        text = req.text.strip()
    return done_response(req, text or "Пустое сообщение.")
