import json
import logging
import time
from typing import Any, Dict, Optional

from src_agent.settings import AGENT_MAX_STEPS, SYSTEM_PROMPT, TIMEOUT_SECONDS
from src_agent.tools.tools import *  # noqa: F403

from src_agent.utils.helpers import normalize_args
from src_agent.utils.mcp_tools import (
    REGISTRY,
    AgentResponse,
    AGentClientCommands,
    AgentClientHandler,
    AgentRegistry,
)

from src_agent.utils.db import (
    Database,
    log_event,
    save_artifact,
    create_intent,
    finish_intent,
    update_session_status,
)

logger = logging.getLogger("src_agent.agent")


def _preview_text(s: Any, limit: int) -> Optional[str]:
    if s is None:
        return None
    if not isinstance(s, str):
        s = str(s)
    return s[:limit]


def _safe_llm_messages(messages: list[dict], preview_limit: int = 200) -> list[dict]:
    out: list[dict] = []
    for m in messages:
        content = m.get("content")
        out.append({
            "role": m.get("role"),
            "len": len(content) if isinstance(content, str) else None,
            "preview": _preview_text(content, preview_limit) if isinstance(content, str) else None,
            "tool_name": m.get("tool_name"),
        })
    return out


class MCPAgent:
    def __init__(
        self,
        nc,
        *,
        llm_subject: str,
        max_steps: int = AGENT_MAX_STEPS,
        timeout_seconds: int = TIMEOUT_SECONDS,
        db: Database,
        user_id: str,
    ):
        self.nc = nc
        self.llm_subject = llm_subject
        self.max_steps = max_steps
        self.timeout_seconds = timeout_seconds

        self.db = db
        self.user_id = user_id

        self.tools = [v["schema"] for v in REGISTRY.values()]
        self.tools_impl = {k: v["fn"] for k, v in REGISTRY.items()}

    async def _request_llm(self, payload: dict) -> dict:
        msg = await self.nc.request(
            self.llm_subject,
            json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            timeout=self.timeout_seconds,
        )
        return json.loads(msg.data.decode("utf-8"))

    def _error(
        self,
        error_type: str,
        message: str | None,
        *,
        prompt: str,
        steps: int,
        model: str | None,
        total_time: float | None = None
    ) -> AgentResponse:
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
        reset_artifacts()  # noqa: F405

        # intent пока хардкод
        intent_id = await create_intent(self.db, session_id=session_id, intent_type="DEFAULT")

        await log_event(
            self.db,
            session_id=session_id,
            intent_id=intent_id,
            role="USER",
            event_type="MESSAGE",
            input={"text": prompt},
        )

        messages = [
            {"role": "system", "content": "\n".join(SYSTEM_PROMPT)},
            {"role": "user", "content": prompt},
        ]

        last_client_handler: AGentClientCommands | None = None
        last_provided_artifacts: list[str] = []
        model_used = None
        start_ts = time.perf_counter()

        try:
            for step in range(1, self.max_steps + 1):
                step_started = time.perf_counter()
                logger.info("STEP %d started", step)

                await log_event(
                    self.db,
                    session_id=session_id,
                    intent_id=intent_id,
                    role="SYSTEM",
                    event_type="STEP_START",
                    input={"step": step},
                )

                llm_payload = {
                    "messages": messages,
                    "tools": self.tools,
                    "think": False,
                    "options": {"temperature": 0.0},
                }

                # safe llm request log
                await log_event(
                    self.db,
                    session_id=session_id,
                    intent_id=intent_id,
                    role="LLM",
                    event_type="LLM_REQUEST",
                    input={
                        "step": step,
                        "tools": [t["function"]["name"] for t in self.tools],
                        "messages": _safe_llm_messages(messages, preview_limit=200),
                        "options": {"temperature": 0.0},
                    },
                )

                try:
                    resp = await self._request_llm(llm_payload)
                except Exception as exc:
                    await log_event(
                        self.db,
                        session_id=session_id,
                        intent_id=intent_id,
                        role="SYSTEM",
                        event_type="ERROR",
                        output={"type": "LLM_EXCEPTION", "message": str(exc), "step": step},
                    )
                    await finish_intent(self.db, intent_id=intent_id, status="FAILED")
                    await update_session_status(self.db, session_id=session_id, status="FAILED")
                    total_time = time.perf_counter() - start_ts
                    return self._error("LLM_EXCEPTION", str(exc), prompt=prompt, steps=step, model=model_used, total_time=total_time)

                if resp.get("error"):
                    await log_event(
                        self.db,
                        session_id=session_id,
                        intent_id=intent_id,
                        role="SYSTEM",
                        event_type="ERROR",
                        output={
                            "type": "LLM_EXCEPTION",
                            "message": resp.get("details") or resp.get("error"),
                            "step": step,
                            "model": resp.get("model") or model_used,
                        },
                    )
                    await finish_intent(self.db, intent_id=intent_id, status="FAILED")
                    await update_session_status(self.db, session_id=session_id, status="FAILED")
                    total_time = time.perf_counter() - start_ts
                    return self._error(
                        "LLM_EXCEPTION",
                        resp.get("details") or resp.get("error"),
                        prompt=prompt,
                        steps=step,
                        model=resp.get("model") or model_used,
                        total_time=total_time,
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

                await log_event(
                    self.db,
                    session_id=session_id,
                    intent_id=intent_id,
                    role="LLM",
                    event_type="LLM_RESPONSE",
                    output={
                        "step": step,
                        "model": model_used,
                        "tool_calls": [{"name": c["function"]["name"]} for c in tool_calls],
                        "content_preview": _preview_text(msg.get("content"), 300),
                    },
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
                    except Exception as exc:
                        await log_event(
                            self.db,
                            session_id=session_id,
                            intent_id=intent_id,
                            role="SYSTEM",
                            event_type="ERROR",
                            name=name,
                            output={"type": "TOOLS_EXCEPTION", "message": f"normalize_args: {exc}", "step": step},
                        )
                        await finish_intent(self.db, intent_id=intent_id, status="FAILED")
                        await update_session_status(self.db, session_id=session_id, status="FAILED")
                        total_time = time.perf_counter() - start_ts
                        return self._error("TOOLS_EXCEPTION", str(exc), prompt=prompt, steps=step, model=model_used, total_time=total_time)

                    await log_event(
                        self.db,
                        session_id=session_id,
                        intent_id=intent_id,
                        role="TOOL",
                        event_type="TOOL_CALL",
                        name=name,
                        input={"step": step, "args": safe_args},
                    )

                    try:
                        cont, result = self.tools_impl[name](**safe_args)
                    except Exception as exc:
                        logger.info("STEP %d tool_error=%s error=%s", step, name, str(exc))
                        await log_event(
                            self.db,
                            session_id=session_id,
                            intent_id=intent_id,
                            role="SYSTEM",
                            event_type="ERROR",
                            name=name,
                            output={"type": "TOOLS_EXCEPTION", "message": str(exc), "step": step},
                        )
                        await finish_intent(self.db, intent_id=intent_id, status="FAILED")
                        await update_session_status(self.db, session_id=session_id, status="FAILED")
                        total_time = time.perf_counter() - start_ts
                        return self._error("TOOLS_EXCEPTION", str(exc), prompt=prompt, steps=step, model=model_used, total_time=total_time)

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

                    await log_event(
                        self.db,
                        session_id=session_id,
                        intent_id=intent_id,
                        role="TOOL",
                        event_type="TOOL_RESULT",
                        name=name,
                        output={
                            "step": step,
                            "status": result.get("status"),
                            "preview": _preview_text(json.dumps(result, ensure_ascii=False), 800),
                        },
                    )

                    if not cont and result.get("status") == "ok":
                        total_time = time.perf_counter() - start_ts

                        artifacts_payload: Dict[str, Any] = {
                            key: ARTIFACTS[key]  # noqa: F405
                            for key in last_provided_artifacts
                            if key in ARTIFACTS  # noqa: F405
                        }

                        # persist artifacts
                        for k, v in artifacts_payload.items():
                            await save_artifact(
                                self.db,
                                session_id=session_id,
                                intent_id=intent_id,
                                type="AGENT_ARTIFACT",
                                name=k,
                                data=v if isinstance(v, dict) else {"value": v},
                            )

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

                        await log_event(
                            self.db,
                            session_id=session_id,
                            intent_id=intent_id,
                            role="SYSTEM",
                            event_type="FINAL_RESPONSE",
                            output={
                                "success": True,
                                "steps": step,
                                "model": model_used or "unknown",
                                "client_handler": last_client_handler,
                                "provided_artifacts": last_provided_artifacts,
                                "total_time_sec": round(total_time, 3),
                            },
                        )

                        await finish_intent(self.db, intent_id=intent_id, status="DONE")
                        await update_session_status(self.db, session_id=session_id, status="DONE")

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

                    # continue conversation for next loop
                    messages.append({
                        "role": "tool",
                        "tool_name": name,
                        "content": json.dumps(result, ensure_ascii=False),
                    })

                    if not cont:
                        break

            # max steps exceeded
            total_time = time.perf_counter() - start_ts
            await log_event(
                self.db,
                session_id=session_id,
                intent_id=intent_id,
                role="SYSTEM",
                event_type="ERROR",
                output={
                    "type": "MAX_STEPS_EXCEEDED",
                    "steps": self.max_steps,
                    "model": model_used or "unknown",
                    "total_time_sec": round(total_time, 3),
                },
            )
            await finish_intent(self.db, intent_id=intent_id, status="FAILED")
            await update_session_status(self.db, session_id=session_id, status="FAILED")
            return self._error(
                "MAX_STEPS_EXCEEDED",
                None,
                prompt=prompt,
                steps=self.max_steps,
                model=model_used,
                total_time=total_time,
            )

        except Exception as exc:
            # last-resort: если что-то взорвалось не там где ожидали
            total_time = time.perf_counter() - start_ts
            await log_event(
                self.db,
                session_id=session_id,
                intent_id=intent_id,
                role="SYSTEM",
                event_type="ERROR",
                output={"type": "AGENT_EXCEPTION", "message": str(exc), "total_time_sec": round(total_time, 3)},
            )
            await finish_intent(self.db, intent_id=intent_id, status="FAILED")
            await update_session_status(self.db, session_id=session_id, status="FAILED")
            return self._error("AGENT_EXCEPTION", str(exc), prompt=prompt, steps=0, model=model_used, total_time=total_time)
