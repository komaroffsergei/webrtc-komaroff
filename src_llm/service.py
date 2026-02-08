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
    LlmRequest,
    LlmResponse,
    ParamsExtractData,
    ReviseData,
    RoutingDecisionData,
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

        if self.llm_mode == "mock":
            return json.loads(self._mock(req).model_dump_json())

        try:
            if req.mode == "routing_decision":
                data = self._routing_decision(req)
            elif req.mode == "params_extract":
                data = self._params_extract(req)
            elif req.mode == "revise":
                data = self._revise(req)
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

    def _mock(self, req: LlmRequest) -> LlmResponse:
        text = str((req.input or {}).get("text") or "")
        allow = (req.input or {}).get("allowlist_workflows") or []
        allow_set = {str(x) for x in allow} if isinstance(allow, list) else set()

        def _pick(workflow_id: str, reason: str) -> RoutingDecisionData:
            wid = workflow_id if workflow_id in allow_set else (next(iter(allow_set)) if allow_set else workflow_id)
            return RoutingDecisionData(workflow_id=wid, reason=reason, confidence=0.9)

        if req.mode == "routing_decision":
            t = text.lower()
            rus_name_kw = "\u0437\u043e\u0432\u0443\u0442"
            rus_airport_kw = "\u0430\u044d\u0440\u043e\u043f\u043e\u0440\u0442"
            rus_weather_kw = "\u043f\u043e\u0433\u043e\u0434\u0430"
            if (rus_name_kw in t or "name" in t) and "collect_name@1.0.0" in allow_set:
                data = _pick("collect_name@1.0.0", "Name collection keywords detected.")
            elif (rus_airport_kw in t or "airport" in t or rus_weather_kw in t or "weather" in t) and "airports_and_weather@1.0.0" in allow_set:
                data = _pick("airports_and_weather@1.0.0", "Airport/weather keywords detected.")
            elif "echo@1.0.0" in allow_set:
                data = _pick("echo@1.0.0", "Fallback to echo.")
            else:
                return LlmResponse(
                    trace_id=req.trace_id,
                    correlation_id=req.correlation_id,
                    request_id=req.request_id,
                    session_id=req.session_id,
                    ts_ms=now_ts_ms(),
                    ok=False,
                    data=None,
                    error=ErrorInfo(code="no_workflow_selected", message="No workflow selected."),
                )
            return LlmResponse.from_validated_data(request=req, data=data)

        if req.mode == "params_extract":
            required = req.input.get("required_fields") if isinstance(req.input, dict) else None
            required_list = [str(x) for x in required] if isinstance(required, list) else []
            values: dict[str, Any] = {}
            missing: list[str] = []
            for f in required_list:
                if f == "radius_km":
                    import re
                    m = re.search(r"(\\d{1,4})", text)
                    if m:
                        values["radius_km"] = int(m.group(1))
                    else:
                        missing.append("radius_km")
                else:
                    missing.append(f)
            return LlmResponse.from_validated_data(request=req, data=ParamsExtractData(values=values, missing=missing))

        if req.mode == "revise":
            return LlmResponse.from_validated_data(
                request=req,
                data=ReviseData(need_user_input=True, question="Please clarify the request."),
            )

        return LlmResponse(
            trace_id=req.trace_id,
            correlation_id=req.correlation_id,
            request_id=req.request_id,
            session_id=req.session_id,
            ts_ms=now_ts_ms(),
            ok=False,
            data=None,
            error=ErrorInfo(code="unsupported_mode", message=f"Unsupported mode: {req.mode}"),
        )

    def _routing_decision(self, req: LlmRequest) -> RoutingDecisionData:
        data = self._infer_json(req, RoutingDecisionData)
        return RoutingDecisionData.model_validate(data)

    def _params_extract(self, req: LlmRequest) -> ParamsExtractData:
        data = self._infer_json(req, ParamsExtractData)
        return ParamsExtractData.model_validate(data)

    def _revise(self, req: LlmRequest) -> ReviseData:
        data = self._infer_json(req, ReviseData)
        return ReviseData.model_validate(data)

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
