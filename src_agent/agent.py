import json
import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, List

import ollama

from llm_client import LLMClient
from mcp_client import MCPClient
from settings import AGENT_MAX_STEPS, STACK_SERVICE_NAME, OLLAMA_URL, SYSTEM_PROMPT, MAX_STEPS, OLLAMA_MODEL, \
    TIMEOUT_SECONDS
from src_agent.tools.tools import reset_artifacts, ARTIFACTS
# from src_agent.repositories.events import log_event
from src_agent.utils.db import create_session, create_intent, finish_intent, finish_session

from src_agent.utils.nats_logger import NatsLogger
from src_agent.utils.utils import log_step, log_error, normalize_tool_calls, log_llm_response, log_final_answer, \
    log_tool_call, normalize_args, log_tool_result, log_stats, _p, build_tool_state_summary

from src_agent.tools import tools
from src_agent.utils.mcp_tools import REGISTRY

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
            ):
        self.user_id = user_id
        self.current_intent_id = None
        self.nc = nc
        self.llm_client = LLMClient(nc, llm_subject=llm_subject)
        self.mcp_client = MCPClient()
        self.max_steps = max_steps
        self.db = db
        self.nats_logger = NatsLogger(self.nc, events_subject, STACK_SERVICE_NAME)
        self.tools = [v["schema"] for v in REGISTRY.values()]
        self.tools_impl = {k: v["fn"] for k, v in REGISTRY.items()}

    async def run(self, *, prompt: str, session_id: str) -> Dict[str, Any]:
        MAX_MESSAGES = 12
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
        reset_artifacts()
        for step in range(1, MAX_STEPS + 1):
            steps += 1
            log_step(step)
            # --- обновляем tool_state summary ---
            # messages = [
            #     m for m in messages
            #     if not (m["role"] == "system" and m.get("name") == "tool_state")
            # ]

            # messages[0] = {
            #     "role": "system",
            #     # "name": "tool_state",
            #     "content": build_tool_state_summary(tool_history, ARTIFACTS),
            # }

            # --- ограничение контекста ---
            if len(messages) > MAX_MESSAGES:
                messages = messages[:2] + messages[-(MAX_MESSAGES - 2):]

            # intent_id = create_intent(session_id, self.user_id, OLLAMA_URL)
            # messages.insert(2, {
            #     "role": "system",
            #     "content": (
            #         "Текущий запрос пользователя:\n"
            #         f"{prompt}\n\n"
            #         "Запрещено:\n"
            #         "- добавлять новые цели\n"
            #         "- выполнять действия, не связанные с запросом\n"
            #     )
            # })

            try:
                resp = client.chat(
                    model=OLLAMA_MODEL,
                    messages=messages,
                    tools=self.tools,
                    think=False,
                    options={"temperature": 0.0},
                )
            except Exception as e:
                log_error(e)

                # finish_intent(intent_id, "FAILED")
                # finish_session(session_id, "FAILED")

                return {
                    "model": OLLAMA_MODEL,
                    "prompt": prompt,
                    "steps": steps,
                    "total_time_sec": round(time.perf_counter() - start_ts, 3),
                    "status": "FAILED",
                    "error": str(e),
                }

            msg = resp["message"]
            # messages.append(msg)

            tool_calls = normalize_tool_calls(msg.get("tool_calls"))
            log_llm_response(msg.get("content"), tool_calls)

            if not tool_calls:
                _p('>>> No tool calls found!')
                log_final_answer(msg.get("content"))
                msg["tool_calls"] = [{"function": {"name": "no_tool_calls", "arguments": {}}}]
                # return {
                #     "status": "ok",
                #     "result": msg.get("content"),
                #     "steps": step,
                # }
                # break

            for call in msg["tool_calls"]:
                name = call["function"]["name"]
                raw_args = call["function"]["arguments"]

                log_tool_call(name, raw_args)
                try:
                    safe_args = normalize_args(self.tools_impl[name], raw_args)
                    cont, result = self.tools_impl[name](**safe_args)
                except Exception as e:
                    log_error(e)
                    # messages.append({
                    #     "role": "tool",
                    #     "tool_call_id": f"too_call_{name}_step_{step}",
                    #     "name": name,
                    #     "content": f"ERROR: {str(e)}",
                    # })
                    break

                log_tool_result(name, result)

                # ===== TERMINAL TOOL =====
                if not cont and result.get("status") == "ok":
                    # finish_intent(intent_id, result.get('status'))
                    finish_session(session_id, result.get('status'))

                    total = time.perf_counter() - start_ts
                    log_stats(steps, total)

                    return {
                        "status": result.get('status'),
                        "result": result.get("result"),
                        "steps": steps,
                        "total_time_sec": round(total, 3),
                    }


                # messages.append({
                #     "role": "tool",
                #     "tool_name": name,
                #     "content": json.dumps(result, ensure_ascii=False),
                # })
                messages.append({
                    "role": "tool",
                    "tool_call_id": f"too_call_{name}_step_{step}",
                    "tool_name": name,
                    "content": json.dumps(result, ensure_ascii=False),
                })

                if not cont:
                    break

        total = time.perf_counter() - start_ts
        log_stats(steps, total)

