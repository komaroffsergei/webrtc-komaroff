from __future__ import annotations

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
        "Если вопрос непонятен, задай уточняющий вопрос."
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


def _extract_text(resp: LlmResponse) -> str | None:
    """Достает текст ответа из LLM payload для free_speech сценария."""
    if not resp.ok or not isinstance(resp.data, dict):
        return None
    value = resp.data.get("response_text")
    return value.strip() if isinstance(value, str) and value.strip() else None


async def run_free_speech(req: WorkflowRunRequest, io: RuntimeIO, *, dialog_context: str = "") -> WorkflowRunResponse:
    """Выполняет свободный диалог одним вызовом mode=final_response."""
    final_resp = await io.call_llm(
        parent=req,
        mode="final_response",
        input_data={
            "task": FREE_SPEECH_TASK,
            "user_message": req.text,
            "tool_results": [],
            "scenario_context": FREE_SPEECH_CONTEXT,
            "dialog_context": dialog_context,
        },
        constraints={"temperature": 0.4},
    )
    return done_response(req, _extract_text(final_resp) or "Чем могу помочь?")
