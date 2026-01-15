import json
import logging
import time

from src_agent.settings import AGENT_MAX_STEPS, SYSTEM_PROMPT, TIMEOUT_SECONDS
from src_agent.tools.tools import *
from src_agent.utils.db import finish_session
from src_agent.utils.helpers import normalize_args
from src_agent.utils.mcp_tools import REGISTRY, AgentResponse, AGentClientCommands, AgentClientHandler, AgentRegistry

logger = logging.getLogger("src_agent.agent")


class MCPAgent:
    def __init__(
        self,
        nc,
        *,
        llm_subject: str,
        max_steps: int = AGENT_MAX_STEPS,
        timeout_seconds: int = TIMEOUT_SECONDS,
    ):
        self.nc = nc
        self.llm_subject = llm_subject
        self.max_steps = max_steps
        self.timeout_seconds = timeout_seconds
        self.tools = [v["schema"] for v in REGISTRY.values()]
        self.tools_impl = {k: v["fn"] for k, v in REGISTRY.items()}

    async def _request_llm(self, payload: dict) -> dict:
        msg = await self.nc.request(
            self.llm_subject,
            json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            timeout=self.timeout_seconds,
        )
        return json.loads(msg.data.decode("utf-8"))

    def _error(self, error_type: str, message: str | None, *, prompt: str, steps: int, model: str | None,
               total_time: float | None = None) -> AgentResponse:
        data = {
            "model": model or "unknown",
            "prompt": prompt,
            "steps": steps,
        }
        if total_time is not None:
            data["total_time_sec"] = round(total_time, 3)
        error = {"type": error_type}
        if message:
            error["message"] = message
        return {
            "success": False,
            "error": error,
            "data": data,
            "client_handler": {"command": "SHOW_ERROR_MESSAGE"},
        }

    async def run(self, *, prompt: str, session_id: str) -> AgentResponse:
        logger.info("[USER] %s", prompt)
        reset_artifacts()

        messages = [
            {"role": "system", "content": "\n".join(SYSTEM_PROMPT)},
            {"role": "user", "content": prompt},
        ]

        last_client_handler: AGentClientCommands | None = None
        last_provided_artifacts: list[str] = []
        model_used = None
        start_ts = time.perf_counter()

        for step in range(1, self.max_steps + 1):
            step_started = time.perf_counter()
            logger.info("STEP %d started", step)
            try:
                resp = await self._request_llm({
                    "messages": messages,
                    "tools": self.tools,
                    "think": False,
                    "options": {"temperature": 0.0},
                })
            except Exception as exc:
                return self._error("LLM_EXCEPTION", str(exc), prompt=prompt, steps=step, model=model_used)

            if resp.get("error"):
                return self._error(
                    "LLM_EXCEPTION",
                    resp.get("details") or resp.get("error"),
                    prompt=prompt,
                    steps=step,
                    model=resp.get("model") or model_used,
                )

            msg = resp.get("message") or {}
            model_used = resp.get("model") or model_used
            tool_calls = msg.get("tool_calls") or [{"function": {"name": "no_tool_calls", "arguments": {}}}]
            logger.info(
                "STEP %d llm_time=%.3fs tools=%s",
                step,
                time.perf_counter() - step_started,
                ",".join(call["function"]["name"] for call in tool_calls),
            )

            for call in tool_calls:
                name = call["function"]["name"]
                raw_args = call["function"].get("arguments") or {}

                logger.info(
                    "STEP %d tool_call=%s args=%s",
                    step,
                    name,
                    json.dumps(raw_args, ensure_ascii=False),
                )
                try:
                    safe_args = normalize_args(self.tools_impl[name], raw_args)
                    cont, result = self.tools_impl[name](**safe_args)
                except Exception as exc:
                    logger.info("STEP %d tool_error=%s error=%s", step, name, str(exc))
                    return self._error("TOOLS_EXCEPTION", str(exc), prompt=prompt, steps=step, model=model_used)

                tool_meta: AgentRegistry = REGISTRY.get(name, {})
                if tool_meta.get("client_handler"):
                    last_client_handler = tool_meta["client_handler"]
                    last_provided_artifacts = list(tool_meta.get("provides") or [])

                logger.info(
                    "STEP %d tool_result=%s status=%s time=%.3fs response=%s",
                    step,
                    name,
                    result.get("status"),
                    time.perf_counter() - step_started,
                    json.dumps(result, ensure_ascii=False),
                )

                if not cont and result.get("status") == "ok":
                    finish_session(session_id, result.get("status"))

                    total_time = time.perf_counter() - start_ts
                    artifacts_payload = {
                        key: ARTIFACTS[key] for key in last_provided_artifacts if key in ARTIFACTS
                    }
                    client_handler: AgentClientHandler | None = None
                    if last_client_handler:
                        client_handler = {
                            "command": last_client_handler,
                            "artifacts": {
                                "last": last_provided_artifacts[0] if last_provided_artifacts else None,
                                "all": last_provided_artifacts,
                                "payload": artifacts_payload,
                            },
                        }

                    return {
                        "success": True,
                        "data": {
                            "model": model_used or "unknown",
                            "prompt": prompt,
                            "steps": step,
                            "total_time_sec": round(total_time, 3),
                        },
                        "result": result.get("result"),
                        "client_handler": client_handler,
                    }

                messages.append({
                    "role": "tool",
                    "tool_name": name,
                    "content": json.dumps(result, ensure_ascii=False),
                })

                if not cont:
                    break

        total_time = time.perf_counter() - start_ts
        return self._error(
            "MAX_STEPS_EXCEEDED",
            None,
            prompt=prompt,
            steps=self.max_steps,
            model=model_used,
            total_time=total_time,
        )
