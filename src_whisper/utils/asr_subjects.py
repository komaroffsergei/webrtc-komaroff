from __future__ import annotations

from dataclasses import dataclass


VALID_SUBSCRIBE_MODES = {"exact", "wildcard", "both"}


@dataclass(frozen=True, slots=True)
class AsrSubjects:
    prefix: str
    subjects: tuple[str, ...]
    wildcard_subject: str | None
    exact_subject: str | None


def parse_subscribe_mode(value: str) -> str:
    mode = (value or "").strip().lower()
    if mode not in VALID_SUBSCRIBE_MODES:
        raise ValueError(f"Invalid ASR_SUBSCRIBE_MODE: {value!r}")
    return mode


def parse_allowed_suffixes(value: str) -> set[str] | None:
    raw = (value or "").strip()
    if not raw:
        return None
    suffixes = {part.strip() for part in raw.split(",") if part.strip()}
    return suffixes or None


def _contains_wildcards(subject: str) -> bool:
    return "*" in subject or ">" in subject


def normalize_asr_prefix(raw: str) -> tuple[str, str | None, list[str]]:
    """
    Normalize a subject prefix so it ends with a dot.

    If raw already contains a wildcard (`*` or `>`), returns it as `wildcard_subject`
    and derives the prefix as the part before the first wildcard token.
    """
    warnings: list[str] = []
    subject = (raw or "").strip()
    if not subject:
        raise ValueError("NATS_ASR_SUBJECT is empty")

    if not _contains_wildcards(subject):
        prefix = subject if subject.endswith(".") else (subject + ".")
        return prefix, None, warnings

    wildcard_subject = subject
    wildcard_pos = min([p for p in (subject.find("*"), subject.find(">")) if p != -1])
    prefix = subject[:wildcard_pos]
    if prefix and not prefix.endswith("."):
        warnings.append("NATS_ASR_SUBJECT contains wildcard but prefix has no trailing '.'; normalizing it")
        prefix += "."

    if wildcard_pos != len(subject) - 1:
        warnings.append("NATS_ASR_SUBJECT contains wildcard in the middle of the subject; behavior may be unexpected")

    if subject.endswith("."):
        warnings.append("NATS_ASR_SUBJECT ends with '.' and also contains wildcard; check configuration")

    return prefix or "", wildcard_subject, warnings


def build_asr_subjects(raw_subject: str, user_id: str | None, mode: str) -> tuple[AsrSubjects, list[str]]:
    mode = parse_subscribe_mode(mode)
    prefix, wildcard_from_raw, warnings = normalize_asr_prefix(raw_subject)

    exact_subject = (prefix + user_id) if user_id else None
    wildcard_subject = wildcard_from_raw or (prefix + ">")

    subjects: list[str] = []
    if mode in {"exact", "both"}:
        if not exact_subject:
            raise ValueError("USER_ID is required for ASR_SUBSCRIBE_MODE=exact|both")
        subjects.append(exact_subject)
    if mode in {"wildcard", "both"}:
        subjects.append(wildcard_subject)

    # De-duplicate while preserving order.
    deduped: list[str] = []
    seen: set[str] = set()
    for s in subjects:
        if s not in seen:
            deduped.append(s)
            seen.add(s)

    return (
        AsrSubjects(
            prefix=prefix,
            subjects=tuple(deduped),
            wildcard_subject=wildcard_subject,
            exact_subject=exact_subject,
        ),
        warnings,
    )


def subject_suffix(prefix: str, subject: str) -> str | None:
    if not prefix:
        return None
    if not subject.startswith(prefix):
        return None
    return subject[len(prefix) :]


def is_subject_allowed(prefix: str, subject: str, allowed_suffixes: set[str] | None) -> bool:
    if not allowed_suffixes:
        return True
    suffix = subject_suffix(prefix, subject)
    return suffix is not None and suffix in allowed_suffixes

