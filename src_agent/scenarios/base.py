from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict

from src_agent.utils.mcp_tools import AgentClientHandler


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


class Scenario:
    """
    Базовый класс сценария.

    Сценарий — это “мини-обработчик” внутри агента, который управляет одной задачей:
    - получает `state` (состояние сессии) и текст пользователя;
    - при необходимости запрашивает уточнение у пользователя (через `display_request`);
    - вызывает инструменты (tools) и сохраняет результаты как артефакты сценария;
    - возвращает ответ + команду для UI (`client_handler`) и опциональные дополнительные события.

    Важные части `state`:
    - `state["scenario"]`: {"id": str|None, "status": "RUNNING"|"NEEDS_INPUT"|..., "input": dict|None}
    - `state["pending"]`: описание того, что мы ждём от пользователя (field/meta/validation)
    - `state["scenario_artifacts"]`: артефакты, изолированные по `scenario_id`
    - `state["scenario_log"]`: внутренний лог шагов сценария (для отладки/аудита)
    """
    id = "base"
    title = "Base"
    description = "Base scenario."
    input_hints: Dict[str, str] = {}
    input_types: Dict[str, str] = {}
    llm_prompt: str

    def on_user_turn(self, state: Dict[str, Any], prompt: str, turn_id: str) -> None:
        # Единая точка логирования пользовательского сообщения внутри сценария.
        self._log(state, status="RUNNING", kind="USER_TURN", data={"text": prompt}, turn_id=turn_id)

    def maybe_switch(self, state: Dict[str, Any], prompt: str) -> str | None:
        # Хук “переключения” на другой сценарий без LLM-routing.
        # По умолчанию сценарии его не используют.
        return None

    def display_request(
        self,
        state: Dict[str, Any],
        *,
        field: str,
        prompt_text: str,
        validation_hint: str,
        validation_regex: str | None = None,
        meta: Dict[str, Any] | None = None,
        turn_id: str,
    ) -> AgentClientHandler:
        """
        Поставить сценарий в режим ожидания ввода и вернуть команду UI `ASK_USER_INPUT`.

        Здесь формируется объект `state["pending"]`, который заставляет `MCPAgent`:
        - на следующем сообщении пользователя продолжить этот же сценарий;
        - пропустить routing через select_scenario (чтобы не “потерять” контекст ожидания).
        """
        artifact_name = f"{self.id}.request.{field}.{turn_id}"
        artifact = {
            "field": field,
            "prompt": prompt_text,
            "hint": validation_hint,
        }
        self._store_artifact(state, name=artifact_name, data=artifact)
        self._log(
            state,
            status="NEEDS_INPUT",
            kind="ASK_INPUT",
            data={"field": field, "prompt": prompt_text},
            turn_id=turn_id,
        )
        if isinstance(state.get("scenario"), dict):
            state["scenario"]["status"] = "NEEDS_INPUT"
            state["scenario"]["id"] = self.id
        state["pending"] = {
            "scenario_id": self.id,
            "kind": "input",
            "field": field,
            "prompt": prompt_text,
            "hint": validation_hint,
            "validation_regex": validation_regex,
            "meta": meta,
        }
        return {
            "command": "ASK_USER_INPUT",
            "artifacts": {
                "last": artifact_name,
                "all": [artifact_name],
                "payload": {artifact_name: artifact},
            },
        }

    async def build_clarification_question(
        self,
        *,
        llm_request,
        user_text: str,
        meta: Dict[str, Any],
    ) -> str:
        """
        Сгенерировать один уточняющий вопрос для пользователя через LLM.

        `meta` — машинное описание того, что нам не хватает.
        Обычно сценарии кладут туда:
        - `missing`: список полей
        - `constraints`: короткие подсказки/примеры для полей
        - `reason`: “почему спрашиваем” (для модели, не для пользователя)
        """
        wants_russian = any("\u0400" <= ch <= "\u04FF" for ch in (user_text or ""))
        lang_hint = (
            "The user writes in Russian. Output must be in Russian."
            if wants_russian
            else "Use the same language as the user."
        )
        payload = {
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You generate a single clarification question for the user.\n"
                        "Rules:\n"
                        f"- {lang_hint}\n"
                        "- Your goal is to collect missing information from the user.\n"
                        "- The missing fields are listed in meta.missing. Ask the user to provide them.\n"
                        "- Use meta.constraints (if present) to add a short example.\n"
                        "- Do not ask about UI (e.g. 'where should I enter'). Ask for the value itself.\n"
                        "- Do not mention scenarios, tools, meta, or system internals.\n"
                        "- Ask naturally; do not require a specific answer format.\n"
                        "- Do not output menus like 'reply with one word'.\n"
                        "- Do not include <think> blocks.\n"
                        "- Output only the question text.\n"
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps({"user_text": user_text, "meta": meta}, ensure_ascii=False),
                },
            ],
            "think": False,
            "options": {"temperature": 0.0},
        }
        resp = await llm_request(payload)
        content = (resp.get("message") or {}).get("content")
        question = content.strip() if isinstance(content, str) else ""
        if not question:
            raise RuntimeError("LLM did not return a clarification question")
        return question

    def display_result(
        self,
        state: Dict[str, Any],
        *,
        result_artifact_name: str,
        summary_text: str,
        data: Dict[str, Any] | None,
        turn_id: str,
        command: str = "SHOW_MESSAGE",
    ) -> AgentClientHandler:
        """
        Завершить сценарий и вернуть результат в UI.

        - сохраняет артефакт результата (summary + data)
        - помечает статус сценария как DONE
        - очищает pending (если он относится к текущему сценарию)
        """
        artifact_name = (
            result_artifact_name
            if result_artifact_name.startswith(f"{self.id}.")
            else f"{self.id}.result.{result_artifact_name}"
        )
        artifact: Dict[str, Any] = {"summary": summary_text}
        if data is not None:
            artifact["data"] = data
        self._store_artifact(state, name=artifact_name, data=artifact)
        self._log(
            state,
            status="DONE",
            kind="RESULT_READY",
            data={"artifact": artifact_name},
            turn_id=turn_id,
        )
        if isinstance(state.get("scenario"), dict):
            state["scenario"]["status"] = "DONE"
        if isinstance(state.get("pending"), dict) and state["pending"].get("scenario_id") == self.id:
            state["pending"] = None
        return {
            "command": command,
            "artifacts": {
                "last": artifact_name,
                "all": [artifact_name],
                "payload": {artifact_name: artifact},
            },
        }

    def _store_artifact(
        self,
        state: Dict[str, Any],
        *,
        name: str,
        data: Dict[str, Any],
    ) -> None:
        # Артефакты сценария хранятся в `state["scenario_artifacts"][scenario_id]`,
        # чтобы разные сценарии не перетирали ключи друг друга.
        scenarios = state.setdefault("scenario_artifacts", {})
        scenario_store = scenarios.get(self.id)
        if scenario_store is None:
            scenario_store = {}
            scenarios[self.id] = scenario_store
        if not isinstance(scenario_store, dict):
            raise RuntimeError("Invalid scenario_artifacts storage type")
        if name in scenario_store:
            raise RuntimeError(f"Artifact key collision: {self.id}.{name}")
        scenario_store[name] = data

    def _log(
        self,
        state: Dict[str, Any],
        *,
        status: str,
        kind: str,
        data: Dict[str, Any],
        turn_id: str | None,
    ) -> None:
        # Внутренний журнал сценария: однотипные записи с timestamp и привязкой к turn_id.
        state.setdefault("scenario_log", []).append({
            "ts": _now_iso(),
            "scenario_id": self.id,
            "status": status,
            "kind": kind,
            "data": data,
            "turn_id": turn_id,
        })
