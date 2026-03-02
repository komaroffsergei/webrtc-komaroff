from __future__ import annotations

from typing import Any

from src_shared.contracts import WorkflowRunRequest, WorkflowRunResponse

DEFAULT_MEMORY_CONTEXT_KEY = "dialog_memory"
DEFAULT_ARTIFACT_CONTEXT_KEY = "artifact_memory"


def memory_from_context(context: dict[str, Any] | None) -> tuple[str, list[dict[str, str]], dict[str, Any]]:
    base = context if isinstance(context, dict) else {}
    extra = {k: v for k, v in base.items() if k != DEFAULT_MEMORY_CONTEXT_KEY}
    payload = base.get(DEFAULT_MEMORY_CONTEXT_KEY)
    if not isinstance(payload, dict):
        payload = {}
    summary = str(payload.get("summary") or "").strip()
    recent = _normalize_turns(payload.get("recent_turns"))
    return summary, recent, extra


def context_with_memory(*, summary: str, recent_turns: list[dict[str, str]], extra: dict[str, Any]) -> dict[str, Any]:
    out = dict(extra or {})
    out[DEFAULT_MEMORY_CONTEXT_KEY] = {
        "summary": str(summary or "").strip(),
        "recent_turns": _normalize_turns(recent_turns),
    }
    return out


def apply_edit_rewrite(
    *,
    summary: str,
    recent_turns: list[dict[str, str]],
    edit_turn_id: str | None,
    recent_messages_limit: int,
    summary_max_chars: int,
) -> tuple[str, list[dict[str, str]]]:
    if not edit_turn_id:
        return compact_memory(summary=summary, recent_turns=recent_turns, recent_messages_limit=recent_messages_limit, summary_max_chars=summary_max_chars)

    idx = -1
    for i, turn in enumerate(recent_turns):
        if turn.get("role") == "user" and turn.get("turn_id") == edit_turn_id:
            idx = i
            break
    if idx < 0:
        return "", []

    # Remove edited user turn and everything after it, then rebuild compact memory.
    rewritten = recent_turns[:idx]
    return compact_memory(summary="", recent_turns=rewritten, recent_messages_limit=recent_messages_limit, summary_max_chars=summary_max_chars)


def compact_memory(
    *,
    summary: str,
    recent_turns: list[dict[str, str]],
    recent_messages_limit: int,
    summary_max_chars: int,
) -> tuple[str, list[dict[str, str]]]:
    normalized = _normalize_turns(recent_turns)
    safe_limit = max(2, int(recent_messages_limit))
    safe_summary_max = max(200, int(summary_max_chars))
    if len(normalized) <= safe_limit:
        return _trim_tail(summary, safe_summary_max), normalized
    overflow = normalized[:-safe_limit]
    kept = normalized[-safe_limit:]
    next_summary = _merge_summary(summary, overflow, safe_summary_max)
    return next_summary, kept


def build_dialog_context(
    *,
    summary: str,
    recent_turns: list[dict[str, str]],
    extra: dict[str, Any] | None,
    max_chars: int,
) -> str:
    sections: list[str] = []
    artifact_block = _artifact_context_block(extra)
    if artifact_block:
        sections.append(artifact_block)
    if summary.strip():
        sections.append(f"Summary:\n{summary.strip()}")
    if recent_turns:
        lines = [
            f"- {_role_label(turn['role'])}: {turn['text']}"
            for turn in recent_turns
        ]
        sections.append("Recent turns:\n" + "\n".join(lines))
    text = "\n\n".join(sections).strip()
    return _trim_tail(text, max(300, int(max_chars)))


def append_exchange(
    *,
    recent_turns: list[dict[str, str]],
    user_turn_id: str,
    user_text: str,
    assistant_turn_id: str,
    assistant_text: str,
) -> list[dict[str, str]]:
    out = list(_normalize_turns(recent_turns))
    out.append(_turn("user", user_turn_id, user_text))
    if assistant_text.strip():
        out.append(_turn("assistant", assistant_turn_id, assistant_text))
    return out


def extract_edit_turn_id(edit: Any) -> str | None:
    if not isinstance(edit, dict):
        return None
    raw = edit.get("turn_id")
    if not isinstance(raw, str):
        return None
    value = raw.strip()
    return value or None


def response_message_text(resp: WorkflowRunResponse) -> str:
    if isinstance(resp.result, str) and resp.result.strip():
        return resp.result.strip()
    payload = resp.client_handler.get("payload") if isinstance(resp.client_handler, dict) else None
    if isinstance(payload, dict):
        for key in ("message", "summary", "prompt"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    if resp.errors and isinstance(resp.errors[0].message, str):
        return resp.errors[0].message.strip()
    return ""


def prepare_dialog_memory(
    *,
    req: WorkflowRunRequest,
    recent_messages_limit: int,
    summary_max_chars: int,
    context_max_chars: int,
) -> dict[str, Any]:
    summary, recent_turns, extra = memory_from_context(req.runtime.context if isinstance(req.runtime.context, dict) else None)
    summary, recent_turns = apply_edit_rewrite(
        summary=summary,
        recent_turns=recent_turns,
        edit_turn_id=extract_edit_turn_id(req.edit),
        recent_messages_limit=recent_messages_limit,
        summary_max_chars=summary_max_chars,
    )
    return {
        "summary": summary,
        "recent_turns": recent_turns,
        "context_extra": extra,
        "dialog_context": build_dialog_context(
            summary=summary,
            recent_turns=recent_turns,
            extra=extra,
            max_chars=context_max_chars,
        ),
    }


def _turn(role: str, turn_id: str, text: str) -> dict[str, str]:
    return {
        "role": "assistant" if role.strip().lower() == "assistant" else "user",
        "turn_id": turn_id.strip(),
        "text": text.strip(),
    }


def _normalize_turns(raw: Any) -> list[dict[str, str]]:
    if not isinstance(raw, list):
        return []
    out: list[dict[str, str]] = []
    for row in raw:
        if not isinstance(row, dict):
            continue
        role = str(row.get("role") or "").strip().lower()
        turn_id = str(row.get("turn_id") or "").strip()
        text = str(row.get("text") or "").strip()
        if role not in {"user", "assistant"} or not turn_id or not text:
            continue
        out.append({"role": role, "turn_id": turn_id, "text": _single_line(text, 500)})
    return out


def _merge_summary(current: str, overflow: list[dict[str, str]], summary_max_chars: int) -> str:
    rows = [f"{_role_label(row['role'])}: {_single_line(row['text'], 200)}" for row in overflow]
    merged = current.strip()
    chunk = " | ".join(rows).strip()
    if not chunk:
        return _trim_tail(merged, summary_max_chars)
    merged = f"{merged} | {chunk}".strip(" |")
    return _trim_tail(merged, summary_max_chars)


def _single_line(text: str, limit: int) -> str:
    one_line = " ".join(str(text or "").split())
    return one_line if len(one_line) <= limit else f"{one_line[: max(1, limit - 14)]}...<truncated>"


def _trim_tail(text: str, max_chars: int) -> str:
    clean = str(text or "").strip()
    if len(clean) <= max_chars:
        return clean
    return f"...{clean[-max_chars:]}"


def _role_label(role: str) -> str:
    return "User" if role == "user" else "Assistant"


def _artifact_context_block(extra: dict[str, Any] | None) -> str:
    if not isinstance(extra, dict):
        return ""
    artifact = extra.get(DEFAULT_ARTIFACT_CONTEXT_KEY)
    if not isinstance(artifact, dict):
        return ""

    sections: list[str] = []
    airports = artifact.get("last_airports")
    if isinstance(airports, list) and airports:
        lines: list[str] = []
        for row in airports[:5]:
            if not isinstance(row, dict):
                continue
            name = str(row.get("name") or "").strip()
            code = str(row.get("code") or "").strip()
            ident = f"{name} ({code})".strip() if name and code else (name or code)
            if not ident:
                continue
            status = str(row.get("status") or "").strip()
            lines.append(f"- {ident}{f', status={status}' if status else ''}")
        if lines:
            sections.append("Recent airports:\n" + "\n".join(lines))

    position = artifact.get("last_position")
    if isinstance(position, dict):
        city = str(position.get("city") or "").strip()
        lat = position.get("lat")
        lon = position.get("lon")
        parts: list[str] = []
        if city:
            parts.append(f"city={city}")
        if lat is not None and lon is not None:
            parts.append(f"coords=({lat},{lon})")
        if parts:
            sections.append("Recent position: " + ", ".join(parts))

    route = artifact.get("last_route")
    if isinstance(route, dict):
        distance = route.get("distance_km")
        if distance is not None:
            sections.append(f"Recent route distance_km={distance}")

    return "\n".join(sections).strip()
