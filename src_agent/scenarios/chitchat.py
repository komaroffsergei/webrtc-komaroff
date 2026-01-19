from __future__ import annotations

import re
from typing import Any, Dict

from src_agent.scenarios.base import Scenario
from src_agent.settings import (
    CHITCHAT_FALLBACK_MESSAGE,
    CHITCHAT_SYSTEM_PROMPT,
    SCENARIO_CHITCHAT_DESC,
    SCENARIO_CHITCHAT_TITLE,
)
from src_agent.utils.db import add_turn


class ChitChatScenario(Scenario):
    id = "chitchat"
    title = SCENARIO_CHITCHAT_TITLE
    description = SCENARIO_CHITCHAT_DESC

    async def handle(
        self,
        state: Dict[str, Any],
        *,
        prompt: str,
        turn_id: str,
        session_id: str,
        intent_id: str,
        db,
        llm_request,
    ):
        self.on_user_turn(state, prompt, turn_id)
        messages = self._build_messages(state)
        llm_payload = {
            "messages": messages,
            "think": False,
            "options": {"temperature": 0.2},
        }
        resp = await llm_request(llm_payload)
        content = (resp.get("message") or {}).get("content")
        reply_text = self._strip_think(content) if isinstance(content, str) else ""
        if not reply_text:
            reply_text = CHITCHAT_FALLBACK_MESSAGE

        handler = self.display_result(
            state,
            result_artifact_name="chitchat_message",
            summary_text=reply_text,
            data={"text": reply_text},
            turn_id=turn_id,
        )
        add_turn(state, role="assistant", text=reply_text)
        return {
            "success": True,
            "result": reply_text,
            "client_handler": handler,
        }

    def _build_messages(self, state: Dict[str, Any]) -> list[dict]:
        messages: list[dict] = [{
            "role": "system",
            "content": CHITCHAT_SYSTEM_PROMPT,
        }]
        for t in state.get("turns", []):
            role = t.get("role")
            text = t.get("text")
            if role in ("user", "assistant") and isinstance(text, str):
                messages.append({"role": role, "content": text})
        return messages

    def _strip_think(self, text: str) -> str:
        cleaned = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
        return cleaned
