from __future__ import annotations

import json
from hashlib import sha256
from typing import Any

from src_agent.utils.nats_logger import NatsLogger
from src_shared.contracts import AgentInboundRequest, WorkflowRunResponse


class UiEventPublisher:
    def __init__(self, nats_logger: NatsLogger) -> None:
        self.nats_logger = nats_logger

    async def publish(self, req: AgentInboundRequest, resp: WorkflowRunResponse) -> None:
        trace = {
            "trace_id": str(req.trace_id),
            "correlation_id": str(req.correlation_id or req.trace_id),
            "request_id": str(req.request_id),
            "session_id": str(resp.session_id) if resp.session_id else None,
        }

        sent: set[str] = set()
        thought_handlers: list[dict[str, Any]] = []
        regular_handlers: list[dict[str, Any]] = []

        for ev in _normalize_client_events(resp.client_events):
            (thought_handlers if _is_thought_handler(ev) else regular_handlers).append(ev)

        if resp.client_handler:
            (thought_handlers if _is_thought_handler(resp.client_handler) else regular_handlers).append(resp.client_handler)

        for handler in thought_handlers:
            await self._publish_client_command(handler, trace, sent)

        msg_text = _extract_result_message(resp)
        if msg_text and not _has_duplicate_client_message(resp, msg_text):
            await self.nats_logger.log(
                "command",
                "message",
                {"type": "answer" if resp.status != "FAILED" else "system", "text": msg_text, "trace": trace},
            )

        for handler in regular_handlers:
            await self._publish_client_command(handler, trace, sent)

        if resp.status == "FAILED" and resp.errors and not _has_explicit_error_command(resp):
            await self._publish_client_command(
                {
                    "command": "SHOW_ERROR_MESSAGE",
                    "payload": {"message": resp.errors[0].message, "code": resp.errors[0].code},
                },
                trace,
                sent,
            )

    async def _publish_client_command(
        self,
        handler: dict[str, Any],
        trace: dict[str, Any],
        sent: set[str],
    ) -> None:
        fp = _fingerprint_client_command(handler)
        if fp in sent:
            return
        sent.add(fp)

        command = handler.get("command")
        if not isinstance(command, str) or not command.strip():
            return
        command_name = command.strip()

        if _is_thought_command(command_name):
            data = _thought_event_data(handler.get("payload"), trace)
            if data:
                await self.nats_logger.log("command", "thought", data)
            return

        artifacts = _payload_to_artifacts(handler.get("payload"))
        data: dict[str, Any] = {"command": command_name, "trace": trace}
        if artifacts:
            data["artifacts"] = artifacts
        await self.nats_logger.log("command", "client", data)


def _extract_result_message(resp: WorkflowRunResponse) -> str | None:
    if isinstance(resp.result, str) and resp.result.strip():
        return resp.result.strip()
    if resp.errors:
        first = resp.errors[0]
        if isinstance(first.message, str) and first.message.strip():
            return first.message.strip()
    return None


def _normalize_client_events(events: Any) -> list[dict[str, Any]]:
    if not isinstance(events, list):
        return []
    return [e for e in events if isinstance(e, dict)]


def _has_duplicate_client_message(resp: WorkflowRunResponse, msg_text: str) -> bool:
    target = msg_text.strip()
    if not target:
        return False
    if _client_command_message_text(resp.client_handler) == target:
        return True
    for ev in _normalize_client_events(resp.client_events):
        if _client_command_message_text(ev) == target:
            return True
    return False


def _client_command_message_text(handler: Any) -> str | None:
    if not isinstance(handler, dict):
        return None
    command = handler.get("command")
    if not isinstance(command, str):
        return None
    if command.strip().upper() not in {"SHOW_MESSAGE", "ASK_USER_INPUT", "SHOW_ERROR_MESSAGE"}:
        return None
    payload = handler.get("payload")
    if not isinstance(payload, dict):
        return None
    for key in ("summary", "prompt", "message"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _has_explicit_error_command(resp: WorkflowRunResponse) -> bool:
    def _is_error_cmd(cmd: Any) -> bool:
        return isinstance(cmd, str) and cmd.strip().upper().startswith("SHOW_ERROR")

    if resp.client_handler and _is_error_cmd(resp.client_handler.get("command")):
        return True
    return any(_is_error_cmd(ev.get("command")) for ev in _normalize_client_events(resp.client_events))


def _is_thought_command(command: str) -> bool:
    return command.strip().upper() in {"SHOW_THOUGHT", "EMIT_THOUGHT"}


def _is_thought_handler(handler: Any) -> bool:
    return isinstance(handler, dict) and isinstance(handler.get("command"), str) and _is_thought_command(handler["command"])


def _thought_event_data(payload: Any, trace: dict[str, Any]) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    summary = payload.get("summary")
    content = payload.get("content")
    scenario = payload.get("scenario")
    tools = payload.get("tools")

    data: dict[str, Any] = {"summary": "Thinking…", "trace": trace}
    if isinstance(summary, str) and summary.strip():
        data["summary"] = summary.strip()
    if isinstance(content, str) and content.strip():
        data["content"] = content.strip()
    if isinstance(scenario, dict):
        sid = scenario.get("id")
        reason = scenario.get("reason")
        out_scenario: dict[str, Any] = {}
        if isinstance(sid, str) and sid.strip():
            out_scenario["id"] = sid.strip()
        if isinstance(reason, str) and reason.strip():
            out_scenario["reason"] = reason.strip()
        if out_scenario:
            data["scenario"] = out_scenario
    if isinstance(tools, list):
        tool_names = [t.strip() for t in tools if isinstance(t, str) and t.strip()]
        if tool_names:
            data["tools"] = tool_names
    return data


def _fingerprint_client_command(handler: dict[str, Any]) -> str:
    try:
        raw = json.dumps(handler, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
    except Exception:
        raw = repr(handler)
    return sha256(raw.encode("utf-8")).hexdigest()


def _payload_to_artifacts(payload: Any) -> dict[str, Any] | None:
    if not isinstance(payload, dict) or not payload:
        return None
    return {"all": ["ui"], "last": "ui", "payload": {"ui": payload}}
