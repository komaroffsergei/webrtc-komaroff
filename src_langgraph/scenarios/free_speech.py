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
        "Используй context_artifacts и dialog_context для референций вроде 'он/этот' и 'они/эти'.\n"
        "При resolved_reference_mode=single не задавай повторный вопрос о том, "
        "что имелось в виду.\n"
        "При resolved_reference_mode=multi и запросе во множественном числе "
        "отвечай по каждой сущности из resolved_entities.\n"
        "Используй не только контекст диалога, но и общие знания модели.\n"
        "Если в знании не уверен, явно укажи неопределенность."
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
_SINGULAR_REF_RE = re.compile(r"\b(он|она|оно|его|ее|её|нему|ней|нем|этот|эта|это|данный|данная)\b", flags=re.IGNORECASE)
_PLURAL_REF_RE = re.compile(r"\b(они|их|ими|эти|этих|этим)\b", flags=re.IGNORECASE)


def _extract_text(resp: LlmResponse) -> str | None:
    """Достает текст ответа из LLM payload для free_speech сценария."""
    if not resp.ok or not isinstance(resp.data, dict):
        return None
    value = resp.data.get("response_text")
    return value.strip() if isinstance(value, str) and value.strip() else None


def _entity_label(entity: dict[str, Any], *, fallback: str = "объект") -> str:
    title = str(entity.get("label") or entity.get("name") or entity.get("title") or "").strip()
    code = str(entity.get("code") or entity.get("id") or entity.get("key") or "").strip()
    if title and code:
        return f"{title} ({code})"
    if title:
        return title
    if code:
        return code
    return fallback


def _tokenize_label(label: str) -> list[str]:
    compact = str(label or "").strip()
    if not compact:
        return []
    parts = re.split(r"[()\s,.;:]+", compact)
    return [p for p in parts if p]


def _looks_like_entity(payload: dict[str, Any]) -> bool:
    identity_keys = ("label", "name", "title", "code", "id", "key")
    for key in identity_keys:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return True
        if key in {"id", "code", "key"} and value is not None and not isinstance(value, (dict, list)):
            return True
    return False


def _extract_entities_from_artifacts(context_extra: dict[str, Any]) -> list[dict[str, Any]]:
    artifact = context_extra.get("artifact_memory")
    if not isinstance(artifact, dict):
        return []

    entities: list[dict[str, Any]] = []

    for key, value in artifact.items():
        if isinstance(value, list):
            for idx, item in enumerate(value[:10], start=1):
                if not isinstance(item, dict) or not _looks_like_entity(item):
                    continue
                label = _entity_label(item, fallback=f"{key}[{idx}]")
                entities.append({"label": label, "source": key, "raw": item})
        elif isinstance(value, dict) and _looks_like_entity(value):
            label = _entity_label(value, fallback=key)
            entities.append({"label": label, "source": key, "raw": value})

    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in entities:
        label = str(row.get("label") or "").strip()
        if not label:
            continue
        key = label.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out


def _explicit_entity_mentions(text: str, entities: list[dict[str, Any]]) -> list[dict[str, Any]]:
    clean = str(text or "")
    lower = clean.lower()
    out: list[dict[str, Any]] = []
    for entity in entities:
        label = str(entity.get("label") or "").strip()
        if not label:
            continue
        if label.lower() in lower:
            out.append(entity)
            continue
        tokens = _tokenize_label(label)
        if any(re.search(rf"\b{re.escape(tok)}\b", clean, flags=re.IGNORECASE) for tok in tokens):
            out.append(entity)
    return out


def _last_assistant_turn(dialog_context: str) -> str:
    lines = [ln.strip() for ln in str(dialog_context or "").splitlines() if ln.strip()]
    assistant_lines = [ln for ln in lines if ln.startswith("- Assistant:")]
    if not assistant_lines:
        return ""
    return assistant_lines[-1]


def _pick_primary_by_recent_assistant(entities: list[dict[str, Any]], dialog_context: str) -> dict[str, Any] | None:
    last_assistant = _last_assistant_turn(dialog_context)
    if not last_assistant:
        return None
    lower = last_assistant.lower()
    matches: list[dict[str, Any]] = []
    for entity in entities:
        label = str(entity.get("label") or "").strip()
        if not label:
            continue
        if label.lower() in lower:
            matches.append(entity)
            continue
        tokens = _tokenize_label(label)
        if any(tok.lower() in lower for tok in tokens):
            matches.append(entity)
    if len(matches) == 1:
        return matches[0]
    return None


def _resolve_entity_reference(
    text: str,
    entities: list[dict[str, Any]],
    *,
    dialog_context: str,
) -> tuple[str, list[dict[str, Any]], str]:
    mentions = _explicit_entity_mentions(text, entities)
    if len(mentions) == 1:
        label = _entity_label(mentions[0])
        return "single", mentions, f"Запрос относится к сущности {label}."
    if len(mentions) > 1:
        labels = ", ".join(_entity_label(a) for a in mentions[:5])
        return "multi", mentions[:5], f"Запрос относится к нескольким сущностям: {labels}."

    plural = bool(_PLURAL_REF_RE.search(text))
    singular = bool(_SINGULAR_REF_RE.search(text))
    if plural and entities:
        labels = ", ".join(_entity_label(a) for a in entities[:5])
        return "multi", entities[:5], f"Запрос относится к сущностям из контекста: {labels}."
    if singular:
        primary = _pick_primary_by_recent_assistant(entities, dialog_context)
        if primary is not None:
            label = _entity_label(primary)
            return "single", [primary], f"Запрос относится к последней фокусной сущности: {label}."
        if len(entities) == 1:
            label = _entity_label(entities[0])
            return "single", [entities[0]], f"В контексте только одна сущность: {label}."
        if len(entities) > 1:
            return "clarify", entities[:5], "Единственное число при нескольких сущностях требует уточнения."
    if len(entities) == 1:
        label = _entity_label(entities[0])
        return "single", [entities[0]], f"В контексте только одна сущность: {label}."
    return "none", [], ""


def _clarify_entity_message(entities: list[dict[str, Any]]) -> str:
    if not entities:
        return "Уточните, о каком объекте речь."
    labels = ", ".join(_entity_label(e) for e in entities[:5])
    return f"Уточните, о каком объекте речь: {labels}."


async def run_free_speech(
    req: WorkflowRunRequest,
    io: RuntimeIO,
    *,
    dialog_context: str = "",
    context_extra: dict[str, Any] | None = None,
) -> WorkflowRunResponse:
    """Выполняет свободный диалог одним вызовом mode=final_response."""
    extra = context_extra if isinstance(context_extra, dict) else {}
    entities = _extract_entities_from_artifacts(extra)
    resolved_mode, resolved_entities, resolved_hint = _resolve_entity_reference(
        req.text or "",
        entities,
        dialog_context=dialog_context,
    )
    if resolved_mode == "clarify":
        return done_response(req, _clarify_entity_message(resolved_entities))

    context_artifacts = extra.get("artifact_memory")
    context_artifacts = context_artifacts if isinstance(context_artifacts, dict) else {}

    llm_input: dict[str, Any] = {
        "task": FREE_SPEECH_TASK,
        "user_message": req.text,
        "tool_results": [],
        "scenario_context": FREE_SPEECH_CONTEXT,
        "dialog_context": dialog_context,
        "context_artifacts": context_artifacts,
        "resolved_reference_mode": resolved_mode if resolved_mode in {"single", "multi"} else "none",
        "resolved_entities": resolved_entities[:5],
        "resolved_hint": resolved_hint,
    }
    final_resp = await io.call_llm(
        parent=req,
        mode="final_response",
        input_data=llm_input,
        constraints={"temperature": 0.4},
    )
    return done_response(req, _extract_text(final_resp) or "Чем могу помочь?")
