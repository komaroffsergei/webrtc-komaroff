from __future__ import annotations

import re
from typing import Any

from src_shared.contracts import LlmResponse, WorkflowRunRequest, WorkflowRunResponse

from src_langgraph.config_loader import dict_value, load_config, text_block
from src_langgraph.responses import done_response
from src_langgraph.runtime_io import RuntimeIO

_CFG = load_config("free_speech")
_PROMPTS = dict_value(_CFG.get("prompts"))
FREE_SPEECH_TASK = text_block(
    _PROMPTS.get("task"),
    (
        "Побеседуй с пользователем в свободной форме.\n"
        "Отвечай кратко, по-русски, дружелюбно и по делу.\n"
        "Если вопрос непонятен, задай уточняющий вопрос.\n"
        "Если в context_artifacts есть ранее найденные объекты (например, аэропорты),"
        " используй их как референты для фраз вроде 'эти аэропорты'.\n"
        "Не выдумывай факты, которых нет в данных."
    ),
)
FREE_SPEECH_CONTEXT = text_block(
    _PROMPTS.get("scenario_context"),
    (
        "Свободный диалог без сценария.\n"
        "Инструменты не используются.\n"
        "Цель — помочь пользователю и поддерживать разговор."
    ),
)
_FOUNDATION_RE = re.compile(r"\b(кем|когда)\b.*\b(основан|основаны|основана|основан[аы]?)\b", flags=re.IGNORECASE)


def _extract_text(resp: LlmResponse) -> str | None:
    """Достает текст ответа из LLM payload для free_speech сценария."""
    if not resp.ok or not isinstance(resp.data, dict):
        return None
    value = resp.data.get("response_text")
    return value.strip() if isinstance(value, str) and value.strip() else None


def _artifact_airports(context_extra: dict[str, Any]) -> list[dict[str, Any]]:
    artifact = context_extra.get("artifact_memory")
    if not isinstance(artifact, dict):
        return []
    airports = artifact.get("last_airports")
    if not isinstance(airports, list):
        return []
    return [a for a in airports if isinstance(a, dict)]


def _foundation_message_for_airports(airports: list[dict[str, Any]]) -> str:
    labels: list[str] = []
    for item in airports[:5]:
        name = str(item.get("name") or "").strip()
        code = str(item.get("code") or "").strip()
        label = f"{name} ({code})".strip() if name and code else (name or code)
        if label:
            labels.append(label)
    if not labels:
        return "В текущих данных нет информации о том, кем и когда основаны эти аэропорты."
    listed = ", ".join(labels)
    return (
        f"В текущих данных нет информации о том, кем и когда основаны аэропорты: {listed}. "
        "Могу помочь с тем, что доступно в сессии: статус, координаты, маршрут и расстояние."
    )


async def run_free_speech(
    req: WorkflowRunRequest,
    io: RuntimeIO,
    *,
    dialog_context: str = "",
    context_extra: dict[str, Any] | None = None,
) -> WorkflowRunResponse:
    """Выполняет свободный диалог одним вызовом mode=final_response."""
    extra = context_extra if isinstance(context_extra, dict) else {}
    airports = _artifact_airports(extra)
    if _FOUNDATION_RE.search(req.text or "") and airports:
        return done_response(req, _foundation_message_for_airports(airports))

    context_artifacts = extra.get("artifact_memory")
    context_artifacts = context_artifacts if isinstance(context_artifacts, dict) else {}

    final_resp = await io.call_llm(
        parent=req,
        mode="final_response",
        input_data={
            "task": FREE_SPEECH_TASK,
            "user_message": req.text,
            "tool_results": [],
            "scenario_context": FREE_SPEECH_CONTEXT,
            "dialog_context": dialog_context,
            "context_artifacts": context_artifacts,
        },
        constraints={"temperature": 0.4},
    )
    return done_response(req, _extract_text(final_resp) or "Чем могу помочь?")
