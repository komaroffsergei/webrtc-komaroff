import json
import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, List

import ollama

from settings import AGENT_MAX_STEPS, STACK_SERVICE_NAME, OLLAMA_URL, SYSTEM_PROMPT, MAX_STEPS, OLLAMA_MODEL
from src_agent.tools.tools import reset_artifacts, ARTIFACTS
from src_agent.utils.db import create_session, create_intent, finish_intent, finish_session

from src_agent.utils.nats_logger import NatsLogger
from src_agent.utils.helpers import normalize_tool_calls, normalize_args

from src_agent.tools import tools
from src_agent.utils.mcp_tools import REGISTRY, build_tool_vocabulary, check_prompt_by_vocabulary, AgentResponse
import logging
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger("src_agent.agent")





class MCPAgent:
    def __init__(self,
                 nc,
                 *,
                 llm_subject: str,
                 events_subject: str,
                 max_steps: int = AGENT_MAX_STEPS,
                 db=None,
                 user_id: str = None,
                 max_messages: int = 12,
            ):
        self.user_id = user_id
        self.current_intent_id = None
        self.nc = nc
        self.max_steps = max_steps
        self.db = db
        self.nats_logger = NatsLogger(self.nc, events_subject, STACK_SERVICE_NAME)
        self.tools = [v["schema"] for v in REGISTRY.values()]
        self.tools_impl = {k: v["fn"] for k, v in REGISTRY.items()}
        self.tools_vocabulary = build_tool_vocabulary()
        self.max_messages = max_messages


    async def run(self, *, prompt: str, session_id: str) -> AgentResponse:
        logger.info("[USER] ----------- New request: %s", prompt)
        reset_artifacts()

        # отбрасываю невалидные запросы
        if not check_prompt_by_vocabulary(prompt, self.tools_vocabulary):
            logger.info("[FINAL ANSWER] %s", "Запрос не поддерживается системой")
            return {
                "model": OLLAMA_MODEL,
                "prompt": prompt,
                "steps": 0,
                "status": "UNSUPPORTED_REQUEST",
                "error": "Запрос не поддерживается системой",
                "data": {
                    "command": {
                        "type": "SHOW_ERROR_MESSAGE",
                    },
                },
            }

        start_ts = time.perf_counter()
        # intent_id = create_intent(
        #     session_id,
        #     self.user_id,
        #     intent_type="GENERIC_QUERY"
        # )

        client = ollama.Client(host=OLLAMA_URL, timeout=60)

        messages = [
            {"role": "system", "content": "\n".join(SYSTEM_PROMPT)},
            {"role": "user", "content": prompt},
        ]

        seq = 0
        steps = 0
        tool_history: List[Dict[str, Any]] = []
        last_final_command: str | None = None
        last_provided_artifacts: list[str] = []

        for step in range(1, MAX_STEPS + 1):
            steps += 1
            logger.debug("STEP %d", step)

            # ограничение контекста
            if len(messages) > self.max_messages:
                messages = messages[:2] + messages[-(self.max_messages - 2):]

            # intent_id = create_intent(session_id, self.user_id, OLLAMA_URL)

            try:
                resp = client.chat(
                    model=OLLAMA_MODEL,
                    messages=messages,
                    tools=self.tools,
                    think=False,
                    options={"temperature": 0.0},
                )
            except Exception as e:
                logger.exception("ERROR: %s", str(e))

                # finish_intent(intent_id, "FAILED")
                # finish_session(session_id, "FAILED")

                return {
                    "model": OLLAMA_MODEL,
                    "prompt": prompt,
                    "steps": steps,
                    "total_time_sec": round(time.perf_counter() - start_ts, 3),
                    "status": "FAILED_EXECUTE",
                    "error": str(e),
                    "data": {
                        "command": {
                            "type": "SHOW_ERROR_MESSAGE",
                        },
                    },
                }

            msg = resp["message"]

            tool_calls = normalize_tool_calls(msg.get("tool_calls"))
            logger.debug("[LLM][content] %s", msg.get("content").strip())
            logger.debug("[LLM][tool_calls]\n%s", json.dumps(tool_calls, ensure_ascii=False, indent=2))

            if not tool_calls:
                logger.warning("[LLM] Модель не вернула tool_calls",)
                msg["tool_calls"] = [{"function": {"name": "no_tool_calls", "arguments": {}}}]

            for call in msg["tool_calls"]:
                name = call["function"]["name"]
                raw_args = call["function"]["arguments"]

                logger.debug("[TOOL CALL] %s\n%s", name, json.dumps(raw_args, ensure_ascii=False, indent=2))
                try:
                    safe_args = normalize_args(self.tools_impl[name], raw_args)
                    cont, result = self.tools_impl[name](**safe_args)
                    # сохраняем финальную команду (для клиента)
                    tool_meta = REGISTRY.get(name, {})
                    if tool_meta.get("final_command"):
                        last_final_command = tool_meta["final_command"]
                        last_provided_artifacts = list(tool_meta.get("provides") or [])

                except Exception as e:
                    logger.exception("ERROR: %s", str(e))
                    return {
                        "model": OLLAMA_MODEL,
                        "prompt": prompt,
                        "steps": 0,
                        "status": "FAILED",
                        "error": f"Ошибка при выполнении инструмента {name}: {str(e)}",
                    }
                    # messages.append({
                    #     "role": "tool",
                    #     "tool_call_id": f"too_call_{name}_step_{step}",
                    #     "name": name,
                    #     "content": f"ERROR: {str(e)}",
                    # })
                    break

                logger.debug("[TOOL RESULT] %s\n%s", name, json.dumps(result, ensure_ascii=False, indent=2))

                # ===== TERMINAL TOOL =====
                if not cont and result.get("status") == "ok":
                    # finish_intent(intent_id, result.get('status'))
                    finish_session(session_id, result.get('status'))

                    total_time = time.perf_counter() - start_ts
                    logger.info("[FINAL ANSWER] %s", result.get("result"))
                    logger.info("STATS steps=%d time=%.3fs", steps, total_time)

                    artifacts_payload = {}

                    for key in last_provided_artifacts:
                        if key in ARTIFACTS:
                            artifacts_payload[key] = ARTIFACTS[key]

                    command = None
                    if last_final_command:
                        command = {
                            "type": last_final_command,
                            "params": {
                                "artifact_key": (
                                    last_provided_artifacts[0]
                                    if len(last_provided_artifacts) == 1
                                    else last_provided_artifacts
                                )
                            }
                        }


                    return {
                        "status": "OK",
                        "model": OLLAMA_MODEL,
                        "prompt": prompt,
                        "steps": steps,
                        "result": result.get("result"),
                        "total_time_sec": round(total_time, 3),
                        "data": {
                            "command": command,
                            "artifacts": artifacts_payload,
                        },
                    }

                messages.append({
                    "role": "tool",
                    "tool_call_id": f"too_call_{name}_step_{step}",
                    "tool_name": name,
                    "content": json.dumps(result, ensure_ascii=False),
                })

                if not cont:
                    break

        total_time = time.perf_counter() - start_ts
        logger.info("STATS steps=%d time=%.3fs", steps, total_time)

        logger.info("[FINAL ANSWER] %s", "MAX_STEPS_EXCEEDED")
        return {
            "status": "FAILED",
            "model": OLLAMA_MODEL,
            "prompt": prompt,
            "steps": steps,
            "error": "MAX_STEPS_EXCEEDED",
            "total_time_sec": round(total_time, 3),
            "data": {
                "command": {
                    "type": "SHOW_ERROR_MESSAGE",
                },
            },
        }


