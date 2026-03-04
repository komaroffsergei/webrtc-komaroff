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
_FACT_QUERY_RE = re.compile(
    r"\b(когда|в каком году|какого года|какой год|какие годы|кем|кто|где|почему|что известно|история|"
    r"год(?:а|у|ом)?(?:\s+(?:основания|постройки|создания|строительства))?|"
    r"основан(?:а|о|ы)?|основание|построен(?:а|о|ы)?|постройк(?:а|и)|"
    r"строительств(?:о|а)|открыт(?:а|о|ы)?|создан(?:а|о|ы)?)\b",
    flags=re.IGNORECASE,
)
_YEAR_QUERY_RE = re.compile(
    r"\b(в каком году|какого года|какой год|какие годы|"
    r"год(?:а|у|ом)?(?:\s+(?:основания|постройки|создания|строительства))?)\b",
    flags=re.IGNORECASE,
)
_YEAR_VALUE_RE = re.compile(r"\b(1[6-9]\d{2}|20\d{2}|21\d{2})\b")
_CONTEXT_ONLY_REFUSAL_HINTS = (
    "в текущих данных нет",
    "в текущем контексте нет",
    "в контексте нет этой информации",
    "в контексте нет данных",
    "в диалоге нет этой информации",
    "в текущем диалоге нет",
    "нет подтвержденной информации",
    "не могу указать",
    "к сожалению, я не уверен",
    "я не уверен, кто",
    "могу помочь с тем, что известно в текущем диалоге",
    "данных о годе",
)
_KNOWLEDGE_RETRY_TASK_SUFFIX = (
    "Если вопрос пользователя требует фактов, не ограничивайся только полями из context_artifacts.\n"
    "Используй общие знания модели вместе с контекстом диалога.\n"
    "Считай context_artifacts подсказками, а не ограничением знаний.\n"
    "Для вопросов про даты/историю/авторство используй знания модели, даже если в context_artifacts нет этих данных.\n"
    "Не отвечай шаблоном о нехватке данных, если факт можно дать из общих знаний.\n"
    "Если уверенность низкая, прямо укажи это в ответе."
)


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


def _is_fact_query(text: str) -> bool:
    clean = str(text or "").strip()
    return bool(clean and (_FACT_QUERY_RE.search(clean) or _YEAR_QUERY_RE.search(clean)))


def _is_year_query(text: str) -> bool:
    clean = str(text or "").strip()
    return bool(clean and _YEAR_QUERY_RE.search(clean))


def _contains_year(text: str) -> bool:
    return bool(_YEAR_VALUE_RE.search(str(text or "")))


def _contains_context_only_refusal(text: str) -> bool:
    lower = str(text or "").lower()
    if not lower:
        return False
    return any(marker in lower for marker in _CONTEXT_ONLY_REFUSAL_HINTS)


def _mentions_resolved_entities(text: str, resolved_entities: list[dict[str, Any]]) -> bool:
    if not resolved_entities:
        return True
    clean = str(text or "")
    if not clean:
        return False
    hits = 0
    for entity in resolved_entities[:5]:
        label = _entity_label(entity).strip()
        if not label:
            continue
        if label.lower() in clean.lower():
            hits += 1
            continue
        tokens = [tok for tok in _tokenize_label(label) if len(tok) >= 3]
        if any(re.search(rf"\b{re.escape(tok)}\b", clean, flags=re.IGNORECASE) for tok in tokens):
            hits += 1
    if len(resolved_entities) <= 1:
        return hits >= 1
    return hits >= min(2, len(resolved_entities))


def _response_quality_score(
    *,
    user_text: str,
    response_text: str,
    resolved_mode: str,
    resolved_entities: list[dict[str, Any]],
) -> int:
    text = str(response_text or "").strip()
    if not text:
        return 0
    score = 1
    if not _contains_context_only_refusal(text):
        score += 2
    if _is_year_query(user_text) and _contains_year(text):
        score += 2
    if resolved_mode in {"single", "multi"} and _mentions_resolved_entities(text, resolved_entities):
        score += 1
    return score


def _needs_knowledge_retry(
    *,
    user_text: str,
    response_text: str,
    resolved_mode: str,
    resolved_entities: list[dict[str, Any]],
) -> bool:
    text = str(response_text or "").strip()
    if not text:
        return True
    if _contains_context_only_refusal(text):
        return True
    if resolved_mode in {"single", "multi"} and not _mentions_resolved_entities(text, resolved_entities):
        return True
    if _is_year_query(user_text) and not _contains_year(text):
        return True
    if _is_fact_query(user_text):
        score = _response_quality_score(
            user_text=user_text,
            response_text=text,
            resolved_mode=resolved_mode,
            resolved_entities=resolved_entities,
        )
        return score < 4
    return False


def _retry_reason(
    *,
    user_text: str,
    response_text: str,
    resolved_mode: str,
    resolved_entities: list[dict[str, Any]],
) -> str:
    text = str(response_text or "").strip()
    if not text:
        return "empty_response"
    if _contains_context_only_refusal(text):
        return "context_only_refusal"
    if _is_year_query(user_text) and not _contains_year(text):
        return "missing_year_for_year_query"
    if resolved_mode in {"single", "multi"} and not _mentions_resolved_entities(text, resolved_entities):
        return "missing_resolved_entity_reference"
    if _is_fact_query(user_text):
        return "low_quality_fact_answer"
    return "generic_secondary_pass"


def _short_dialog_context(dialog_context: str, *, max_lines: int = 10, max_chars: int = 2400) -> str:
    lines = [ln.strip() for ln in str(dialog_context or "").splitlines() if ln.strip()]
    if not lines:
        return ""
    tail = "\n".join(lines[-max_lines:])
    return tail if len(tail) <= max_chars else tail[-max_chars:]


def _retry_context_artifacts(
    *,
    context_artifacts: dict[str, Any],
    resolved_entities: list[dict[str, Any]],
) -> dict[str, Any]:
    if not resolved_entities:
        return context_artifacts
    resolved_raw = [row.get("raw") for row in resolved_entities[:5] if isinstance(row.get("raw"), dict)]
    if not resolved_raw:
        return context_artifacts
    return {"resolved_entities": resolved_raw}


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

    primary_input: dict[str, Any] = {
        "task": FREE_SPEECH_TASK,
        "user_message": req.text,
        "tool_results": [],
        "scenario_context": FREE_SPEECH_CONTEXT,
        "dialog_context": dialog_context,
        "context_artifacts": context_artifacts,
        "resolved_reference_mode": resolved_mode if resolved_mode in {"single", "multi"} else "none",
        "resolved_entities": resolved_entities[:5],
        "resolved_hint": resolved_hint,
        "free_speech_pass": "primary",
    }
    primary_resp = await io.call_llm(
        parent=req,
        mode="final_response",
        input_data=primary_input,
        constraints={"temperature": 0.4},
    )
    if not primary_resp.ok:
        return done_response(req, "Сервис ответов временно недоступен. Попробуйте повторить запрос.")
    primary_text = _extract_text(primary_resp) or ""
    needs_retry = _needs_knowledge_retry(
        user_text=req.text or "",
        response_text=primary_text,
        resolved_mode=resolved_mode,
        resolved_entities=resolved_entities,
    )
    if not needs_retry:
        return done_response(req, primary_text or "Чем могу помочь?")

    retry_reason = _retry_reason(
        user_text=req.text or "",
        response_text=primary_text,
        resolved_mode=resolved_mode,
        resolved_entities=resolved_entities,
    )

    secondary_input: dict[str, Any] = {
        **primary_input,
        "task": f"{FREE_SPEECH_TASK}\n{_KNOWLEDGE_RETRY_TASK_SUFFIX}",
        "dialog_context": _short_dialog_context(dialog_context),
        "context_artifacts": _retry_context_artifacts(
            context_artifacts=context_artifacts,
            resolved_entities=resolved_entities,
        ),
        "free_speech_pass": "knowledge_retry",
        "retry_reason": retry_reason,
    }
    secondary_resp = await io.call_llm(
        parent=req,
        mode="final_response",
        input_data=secondary_input,
        constraints={"temperature": 0.3},
    )
    secondary_text = _extract_text(secondary_resp) or ""

    primary_score = _response_quality_score(
        user_text=req.text or "",
        response_text=primary_text,
        resolved_mode=resolved_mode,
        resolved_entities=resolved_entities,
    )
    secondary_score = _response_quality_score(
        user_text=req.text or "",
        response_text=secondary_text,
        resolved_mode=resolved_mode,
        resolved_entities=resolved_entities,
    )
    best_text = secondary_text if secondary_score >= primary_score else primary_text
    return done_response(req, best_text or primary_text or "Чем могу помочь?")
