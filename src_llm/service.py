import asyncio
import json
import logging
import threading
from pathlib import Path
from typing import Any
from uuid import uuid4

import ollama
from nats.aio.msg import Msg
from pydantic import BaseModel

from src_llm.clients.local_chat import chat as local_chat
from src_llm.clients.ollama_chat import chat as ollama_chat
from src_llm.settings import STACK_SERVICE_NAME
from src_llm.utils.base_service import BaseService
from src_llm.utils.model_downloader import ensure_model_path
from src_shared.contracts import (
    ErrorInfo,
    FinalResponseData,
    LlmRequest,
    LlmResponse,
    ParamsExtractData,
    ReviseData,
    RoutingDecisionData,
    ToolDecisionData,
    ToolParamsData,
    now_ts_ms,
)

logger = logging.getLogger(STACK_SERVICE_NAME)

class LLMService(BaseService):
    def __init__(
        self,
        *,
        service_name: str,
        nats_url: str,
        llm_subject: str,
        events_subject: str,
        ollama_url: str,
        llm_local_model: str,
        llm_remote_model: str,
        default_max_tokens: int,
        llm_mode: str,
        llm_models_dir: str,
        ollama_model_file: str,
        llm_context_size: int,
    ) -> None:
        super().__init__(
            service_name=service_name,
            nats_url=nats_url,
            llm_subject=llm_subject,
            events_subject=events_subject,
        )
        self.llm_local_model = llm_local_model
        self.llm_remote_model = llm_remote_model
        self.default_max_tokens = int(default_max_tokens)
        self.llm_mode = (llm_mode or "remote").strip().lower()
        if self.llm_mode not in {"local", "remote"}:
            raise ValueError("LLM_MODE must be either 'local' or 'remote'")
        self.llm_models_dir = llm_models_dir
        self.ollama_model_file = (ollama_model_file or "").strip() or None
        self.llm_context_size = int(llm_context_size)
        self._use_local = self.llm_mode == "local"
        self._ollama = None if self._use_local else ollama.Client(host=ollama_url)
        self._local_model = None
        self._inference_lock = threading.Lock()

    async def on_run(self) -> None:
        await self._nats_logger.info(
            f"{STACK_SERVICE_NAME} service connected (mode={self.llm_mode})"
        )
        if self._use_local:
            await self._nats_logger.log("command", "status_llm", {"status": "downloading"})
            await asyncio.to_thread(
                ensure_model_path,
                self.llm_local_model,
                self.llm_models_dir,
                self.ollama_model_file,
            )
            await self._nats_logger.log("command", "status_llm", {"status": "ready"})

    def _ensure_local_model(self):
        if self._local_model:
            return self._local_model

        model_path = ensure_model_path(
            self.llm_local_model,
            self.llm_models_dir,
            self.ollama_model_file,
        )
        logger.info("Loading local model from %s", model_path)

        from llama_cpp import Llama

        init_kwargs = {
            "model_path": model_path,
            "n_ctx": self.llm_context_size,
        }
        self._local_model = Llama(**init_kwargs)
        return self._local_model

    def on_message(self, msg: Msg) -> dict[str, Any]:
        raw = json.loads(msg.data.decode("utf-8"))
        try:
            req = LlmRequest.model_validate(raw)
        except Exception as exc:
            resp = LlmResponse(
                trace_id=uuid4(),
                correlation_id=None,
                request_id=uuid4(),
                session_id=None,
                ts_ms=now_ts_ms(),
                ok=False,
                data=None,
                error=ErrorInfo(code="invalid_request", message=str(exc)),
            )
            return json.loads(resp.model_dump_json())

        try:
            if req.mode == "routing_decision":
                data = self._routing_decision(req)
            elif req.mode == "params_extract":
                data = self._params_extract(req)
            elif req.mode == "revise":
                data = self._revise(req)
            elif req.mode == "tool_decision":
                data = self._tool_decision(req)
            elif req.mode == "tool_params":
                data = self._tool_params(req)
            elif req.mode == "final_response":
                data = self._final_response(req)
            else:
                raise ValueError(f"Unsupported mode: {req.mode}")
            return json.loads(LlmResponse.from_validated_data(request=req, data=data).model_dump_json())
        except Exception as exc:
            resp = LlmResponse(
                trace_id=req.trace_id,
                correlation_id=req.correlation_id,
                request_id=req.request_id,
                session_id=req.session_id,
                ts_ms=now_ts_ms(),
                ok=False,
                data=None,
                error=ErrorInfo(code="llm_failed", message=str(exc)),
            )
            return json.loads(resp.model_dump_json())

    def _routing_decision(self, req: LlmRequest) -> RoutingDecisionData:
        data = self._infer_json(req, RoutingDecisionData)
        inp = req.input if isinstance(req.input, dict) else {}
        text = str(inp.get("text") or "").lower()
        allow_raw = inp.get("allowlist_workflows")
        allowlist = [str(x) for x in allow_raw] if isinstance(allow_raw, list) else []
        allowset = set(allowlist)

        def _fallback() -> RoutingDecisionData:
            if (
                ("зовут" in text or "name" in text)
                and "collect_name@1.0.0" in allowset
            ):
                return RoutingDecisionData(
                    workflow_id="collect_name@1.0.0",
                    reason="fallback keyword routing: name",
                    confidence=0.6,
                )
            if (
                any(k in text for k in ["аэропорт", "airport", "погода", "weather"])
                and "airports_and_weather@1.0.0" in allowset
            ):
                return RoutingDecisionData(
                    workflow_id="airports_and_weather@1.0.0",
                    reason="fallback keyword routing: airport/weather",
                    confidence=0.6,
                )
            if "echo@1.0.0" in allowset:
                return RoutingDecisionData(
                    workflow_id="echo@1.0.0",
                    reason="fallback default routing: echo",
                    confidence=0.4,
                )
            if allowlist:
                return RoutingDecisionData(
                    workflow_id=allowlist[0],
                    reason="fallback default routing: first allowlist item",
                    confidence=0.3,
                )
            raise ValueError("No workflow selected and allowlist is empty")

        try:
            parsed = RoutingDecisionData.model_validate(data)
        except Exception:
            # Be tolerant to slightly off-schema model outputs.
            workflow_id = str(
                data.get("workflow_id")
                or data.get("workflow")
                or data.get("scenario_id")
                or ""
            ).strip()
            if not workflow_id:
                return _fallback()

            reason = str(data.get("reason") or "normalized routing decision").strip()
            try:
                confidence = float(data.get("confidence", 0.5))
            except Exception:
                confidence = 0.5
            confidence = max(0.0, min(1.0, confidence))
            parsed = RoutingDecisionData(
                workflow_id=workflow_id,
                reason=reason or "normalized routing decision",
                confidence=confidence,
            )

        if allowset and parsed.workflow_id not in allowset:
            return _fallback()
        return parsed

    def _params_extract(self, req: LlmRequest) -> ParamsExtractData:
        data = self._infer_json(req, ParamsExtractData)
        try:
            return ParamsExtractData.model_validate(data)
        except Exception:
            # Normalize flat outputs like {"city":"Moscow","radius_km":25}
            # into strict schema {"ok","values","missing","confidence","notes"}.
            inp = req.input if isinstance(req.input, dict) else {}
            spec = inp.get("spec") if isinstance(inp.get("spec"), dict) else {}
            fields = spec.get("fields") if isinstance(spec.get("fields"), dict) else {}
            requested = [str(k) for k in fields.keys()]

            values: dict[str, Any] = {}
            for key in requested:
                if key in data and data[key] is not None and str(data[key]).strip() != "":
                    values[key] = data[key]

            # If spec is missing, fallback to all non-meta keys.
            if not requested:
                for key, value in data.items():
                    if key in {"ok", "values", "missing", "confidence", "notes"}:
                        continue
                    if value is None or (isinstance(value, str) and value.strip() == ""):
                        continue
                    values[str(key)] = value

            missing = [key for key in requested if key not in values]
            confidence_raw = data.get("confidence", 0.75 if values else 0.25)
            try:
                confidence = float(confidence_raw)
            except Exception:
                confidence = 0.25
            confidence = max(0.0, min(1.0, confidence))

            return ParamsExtractData(
                ok=len(missing) == 0,
                values=values,
                missing=missing,
                confidence=confidence,
                notes=["normalized_from_flat_json"],
            )

    def _revise(self, req: LlmRequest) -> ReviseData:
        data = self._infer_json(req, ReviseData)
        return ReviseData.model_validate(data)

    def _tool_decision(self, req: LlmRequest) -> ToolDecisionData:
        """LLM decides which tool to call based on user message and available tools."""
        data = self._infer_json(req, ToolDecisionData)
        try:
            return ToolDecisionData.model_validate(data)
        except Exception:
            # Normalize output
            needs_tool = bool(data.get("needs_tool", True))
            tool_name = data.get("tool_name")
            reason = str(data.get("reason") or "no reason provided").strip()
            if not needs_tool:
                return ToolDecisionData(needs_tool=False, tool_name=None, reason=reason)
            if not tool_name:
                raise ValueError("tool_name is required when needs_tool=true")
            return ToolDecisionData(needs_tool=True, tool_name=str(tool_name), reason=reason)

    def _tool_params(self, req: LlmRequest) -> ToolParamsData:
        """LLM extracts parameters for tool execution."""
        data = self._infer_json(req, ToolParamsData)
        try:
            return ToolParamsData.model_validate(data)
        except Exception:
            # Normalize output
            extracted = data.get("extracted") or {}
            if not isinstance(extracted, dict):
                extracted = {}
            missing = data.get("missing") or []
            if not isinstance(missing, list):
                missing = []
            prompt = data.get("prompt")
            if prompt and not isinstance(prompt, str):
                prompt = str(prompt)
            return ToolParamsData(
                extracted=extracted,
                missing=[str(m) for m in missing],
                prompt=prompt if prompt else None,
            )

    def _final_response(self, req: LlmRequest) -> FinalResponseData:
        """LLM generates final response to user."""
        data = self._infer_json(req, FinalResponseData)
        try:
            return FinalResponseData.model_validate(data)
        except Exception:
            response_text = data.get("response_text") or data.get("response") or ""
            if not isinstance(response_text, str) or not response_text.strip():
                raise ValueError("response_text is required")
            client_command = data.get("client_command")
            if client_command and not isinstance(client_command, dict):
                client_command = None
            return FinalResponseData(response_text=str(response_text), client_command=client_command)

    def _infer_json(self, req: LlmRequest, schema: type[BaseModel]) -> dict[str, Any]:
        schema_json = schema.model_json_schema()
        system = (
            "You are a service that must return ONLY a single JSON object.\n"
            "Do not wrap it in markdown. Do not add any extra keys.\n"
            "Validate against this JSON Schema and fix formatting if needed:\n"
            f"{json.dumps(schema_json, ensure_ascii=True)}"
        )
        user = json.dumps(req.input or {}, ensure_ascii=True)

        options = dict(req.constraints or {})
        options.setdefault("temperature", 0.0)
        max_tokens = int(options.pop("max_tokens", self.default_max_tokens) or self.default_max_tokens)

        model = options.pop("model", None) or (self.llm_local_model if self._use_local else self.llm_remote_model)

        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]

        if self._use_local:
            with self._inference_lock:
                result = local_chat(
                    self._ensure_local_model(),
                    model=model,
                    messages=messages,
                    tools=[],
                    options=options,
                    max_tokens=max_tokens,
                )
        else:
            result = ollama_chat(
                self._ollama,
                model=model,
                messages=messages,
                tools=[],
                options=options,
                think=False,
            )

        content = (result.get("message") or {}).get("content") or ""
        data = _parse_json_object(str(content))
        if not isinstance(data, dict):
            raise ValueError("Model did not return a JSON object")
        return data


def _parse_json_object(text: str) -> Any:
    raw = (text or "").strip()
    if not raw:
        raise ValueError("Empty model output")

    # Strip common markdown fences if the model ignored instructions.
    if raw.startswith("```"):
        raw = raw.lstrip("`")
        nl = raw.find("\n")
        raw = raw[nl + 1 :] if nl != -1 else raw
        end = raw.rfind("```")
        raw = raw[:end] if end != -1 else raw
        raw = raw.strip()

    dec = json.JSONDecoder()

    # Fast path.
    try:
        obj, _ = dec.raw_decode(raw)
        return obj
    except json.JSONDecodeError:
        pass

    # Best-effort: find the first JSON object and parse only it (ignore trailing junk).
    brace_positions = [i for i, ch in enumerate(raw) if ch == "{"]
    for i in brace_positions[:50]:
        try:
            obj, _ = dec.raw_decode(raw[i:])
            return obj
        except json.JSONDecodeError:
            continue

    raise ValueError("Invalid JSON output")
