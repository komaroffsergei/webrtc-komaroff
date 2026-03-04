import asyncio
import json
import logging
import re
import threading
import time
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
        ollama_timeout_s: float,
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
        self.ollama_timeout_s = float(ollama_timeout_s)
        self._use_local = self.llm_mode == "local"
        self._ollama = None if self._use_local else ollama.Client(host=ollama_url, timeout=self.ollama_timeout_s)
        self._local_model = None
        self._inference_lock = threading.Lock()
        self._inference_meta_lock = threading.Lock()
        self._inference_meta_by_request: dict[str, dict[str, Any]] = {}

    async def on_run(self) -> None:
        await self._nats_logger.info(
            f"{STACK_SERVICE_NAME} service connected (mode={self.llm_mode})"
        )
        await self._nats_logger.info(
            {
                "mode": self.llm_mode,
                "configured_model": self._configured_model(),
                "llm_context_size": self.llm_context_size,
            },
            name="llm_runtime_config",
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

    @staticmethod
    def _routing_input_normalized(inp: dict[str, Any]) -> dict[str, Any]:
        out = dict(inp or {})

        if not out.get("text") and isinstance(out.get("user_message"), str):
            out["text"] = out.get("user_message")

        scenarios = out.get("available_scenarios")
        if isinstance(scenarios, list):
            allowlist: list[str] = []
            for item in scenarios:
                if not isinstance(item, dict):
                    continue
                scenario_id = str(item.get("id") or "").strip()
                if scenario_id:
                    allowlist.append(scenario_id)
            if allowlist and not isinstance(out.get("allowlist_workflows"), list):
                out["allowlist_workflows"] = allowlist

        return out

    @staticmethod
    def _mode_instruction_ru(mode: str) -> str:
        if mode == "routing_decision":
            return (
                "Определи один наиболее подходящий сценарий (workflow) для пользовательского запроса. "
                "Выбирай только из списка allowlist_workflows или available_scenarios[].id. "
                "Учитывай русские формулировки, опечатки и неполные запросы."
            )
        if mode == "params_extract":
            return (
                "Извлеки параметры из сообщения пользователя по заданной спецификации. "
                "Если данных не хватает, верни missing и не выдумывай значения."
            )
        if mode == "revise":
            return (
                "Проверь и исправь структуру данных. Если данных недостаточно, попроси уточнение на русском."
            )
        if mode == "tool_decision":
            return (
                "Выбери следующий инструмент из available_tools. "
                "Если инструмент не нужен, верни needs_tool=false."
            )
        if mode == "tool_params":
            return (
                "Извлеки параметры для вызова инструмента по сообщению пользователя и контексту. "
                "Если параметров не хватает, перечисли missing и сформулируй prompt на русском."
            )
        if mode == "final_response":
            return (
                "Сформируй финальный ответ пользователю на русском языке. "
                "Используй релевантный контекст из dialog_context/context_artifacts/tool_results и общие знания модели. "
                "Если есть неуверенность в фактах, явно укажи это. "
                "Ответ должен быть понятным и без технических деталей внутренней системы."
            )
        return "Верни корректный JSON по схеме."

    def _configured_model(self) -> str:
        return self.llm_local_model if self._use_local else self.llm_remote_model

    def _set_inference_meta(self, request_id: str, meta: dict[str, Any]) -> None:
        if not request_id:
            return
        with self._inference_meta_lock:
            self._inference_meta_by_request[request_id] = dict(meta)

    def _pop_inference_meta(self, request_id: str) -> dict[str, Any]:
        if not request_id:
            return {}
        with self._inference_meta_lock:
            value = self._inference_meta_by_request.pop(request_id, {})
        return value if isinstance(value, dict) else {}

    def _request_debug_extra(self, raw_req: dict[str, Any]) -> dict[str, Any]:
        return {
            "llm_mode": self.llm_mode,
            "configured_model": self._configured_model(),
            "llm_context_size": self.llm_context_size,
            "ollama_timeout_s": self.ollama_timeout_s,
        }

    def _llm_result_debug(
        self,
        payload: Any,
        *,
        req_mode: str | None,
        raw_req: dict[str, Any] | None,
        duration_ms: int,
    ) -> Any:
        if not isinstance(payload, dict):
            return payload
        out = dict(payload)
        request_id = ""
        if isinstance(raw_req, dict):
            request_id = str(raw_req.get("request_id") or "").strip()
        inference_meta = self._pop_inference_meta(request_id)
        out["_debug"] = {
            "duration_ms": max(0, int(duration_ms)),
            **inference_meta,
        }
        return out

    def _routing_decision(self, req: LlmRequest) -> RoutingDecisionData:
        inp_raw = req.input if isinstance(req.input, dict) else {}
        inp = self._routing_input_normalized(inp_raw)
        data = self._infer_json(req.model_copy(update={"input": inp}), RoutingDecisionData)
        text = str(inp.get("text") or "").lower()
        allow_raw = inp.get("allowlist_workflows")
        allowlist = [str(x) for x in allow_raw] if isinstance(allow_raw, list) else []
        allowset = set(allowlist)

        def _fallback() -> RoutingDecisionData:
            flight_keywords = ["рейс", "flight", "авиарейс", "статус рейса", "где мой рейс"]
            route_keywords = [
                "найди аэропорт",
                "найти аэропорт",
                "ближайший аэропорт",
                "nearest airport",
                "маршрут",
                "построй маршрут",
                "аэропорт рядом",
            ]
            if (
                ("where_my_flight@2.0.0" in allowset)
                and (
                    any(k in text for k in flight_keywords)
                    or ("su" in text and any(ch.isdigit() for ch in text))
                )
            ):
                return RoutingDecisionData(
                    workflow_id="where_my_flight@2.0.0",
                    reason="Резервная маршрутизация по ключевым словам: рейс",
                    confidence=0.72,
                )
            if (
                "find_nearest_airport@2.0.0" in allowset
                and any(k in text for k in route_keywords)
            ):
                return RoutingDecisionData(
                    workflow_id="find_nearest_airport@2.0.0",
                    reason="Резервная маршрутизация по ключевым словам: аэропорт/маршрут",
                    confidence=0.72,
                )
            if (
                ("зовут" in text or "name" in text)
                and "collect_name@1.0.0" in allowset
            ):
                return RoutingDecisionData(
                    workflow_id="collect_name@1.0.0",
                    reason="Резервная маршрутизация по ключевому слову: имя",
                    confidence=0.6,
                )
            if (
                any(k in text for k in ["аэропорт", "airport", "погода", "weather"])
                and "airports_and_weather@1.0.0" in allowset
            ):
                return RoutingDecisionData(
                    workflow_id="airports_and_weather@1.0.0",
                    reason="Резервная маршрутизация по ключевым словам: аэропорт/погода",
                    confidence=0.6,
                )
            if "no_found_command@2.0.0" in allowset and text.strip():
                return RoutingDecisionData(
                    workflow_id="no_found_command@2.0.0",
                    reason="Резервная маршрутизация: неизвестная команда",
                    confidence=0.35,
                )
            if "echo@2.0.0" in allowset:
                return RoutingDecisionData(
                    workflow_id="echo@2.0.0",
                    reason="Резервная маршрутизация: echo",
                    confidence=0.3,
                )
            if "echo@1.0.0" in allowset:
                return RoutingDecisionData(
                    workflow_id="echo@1.0.0",
                    reason="Резервная маршрутизация: echo",
                    confidence=0.4,
                )
            if allowlist:
                return RoutingDecisionData(
                    workflow_id=allowlist[0],
                    reason="Резервная маршрутизация: первый элемент allowlist",
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

            reason = str(data.get("reason") or "Нормализованное решение маршрутизации").strip()
            try:
                confidence = float(data.get("confidence", 0.5))
            except Exception:
                confidence = 0.5
            confidence = max(0.0, min(1.0, confidence))
            parsed = RoutingDecisionData(
                workflow_id=workflow_id,
                reason=reason or "Нормализованное решение маршрутизации",
                confidence=confidence,
            )

        normalized_id = self._normalize_routing_workflow_id(parsed.workflow_id, allowset)
        if normalized_id and normalized_id != parsed.workflow_id:
            parsed = parsed.model_copy(update={"workflow_id": normalized_id})

        if allowset and parsed.workflow_id not in allowset:
            return _fallback()
        return parsed

    @staticmethod
    def _normalize_routing_workflow_id(workflow_id: str, allowset: set[str]) -> str | None:
        raw = str(workflow_id or "").strip()
        if not raw:
            return None
        if raw in allowset:
            return raw

        def _norm(value: str) -> str:
            return re.sub(r"[^a-z0-9]+", "", value.lower())

        key = _norm(raw)
        alias_map = {
            "wheremyflight200": "where_my_flight@2.0.0",
            "wheremyflight": "where_my_flight@2.0.0",
            "whereismyflight": "where_my_flight@2.0.0",
            "flightstatuscheck": "where_my_flight@2.0.0",
            "flightstatus": "where_my_flight@2.0.0",
            "flightstatuslookup": "where_my_flight@2.0.0",
            "findnearestairport200": "find_nearest_airport@2.0.0",
            "findnearestairport": "find_nearest_airport@2.0.0",
            "nearestairportroute": "find_nearest_airport@2.0.0",
            "nearestairport": "find_nearest_airport@2.0.0",
            "echo200": "echo@2.0.0",
            "echo": "echo@2.0.0",
            "nofoundcommand200": "no_found_command@2.0.0",
            "nofoundcommand": "no_found_command@2.0.0",
            "unknowncommand": "no_found_command@2.0.0",
            "unknown": "no_found_command@2.0.0",
        }
        mapped = alias_map.get(key)
        if not mapped:
            return raw
        if allowset and mapped not in allowset:
            return raw
        return mapped

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
            parsed = ToolParamsData.model_validate(data)
            return self._postprocess_tool_params(req, parsed)
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
            parsed = ToolParamsData(
                extracted=extracted,
                missing=[str(m) for m in missing],
                prompt=prompt if prompt else None,
            )
            return self._postprocess_tool_params(req, parsed)

    def _postprocess_tool_params(self, req: LlmRequest, parsed: ToolParamsData) -> ToolParamsData:
        inp = req.input if isinstance(req.input, dict) else {}
        tool_name = str(inp.get("tool_name") or "").strip()
        user_message = str(inp.get("user_message") or "").strip()
        tool_results = inp.get("tool_results") if isinstance(inp.get("tool_results"), list) else []

        extracted = dict(parsed.extracted or {})
        missing = [str(m) for m in (parsed.missing or [])]
        prompt = parsed.prompt if isinstance(parsed.prompt, str) and parsed.prompt.strip() else None

        def _latest_tool_result(name: str) -> dict[str, Any] | None:
            for item in reversed(tool_results):
                if not isinstance(item, dict):
                    continue
                if str(item.get("tool_name") or "").strip() != name:
                    continue
                result = item.get("result")
                if isinstance(result, dict):
                    return result
            return None

        def _to_float(v: Any) -> float | None:
            if isinstance(v, (int, float)):
                return float(v)
            if isinstance(v, str):
                try:
                    return float(v.strip())
                except Exception:
                    return None
            return None

        if tool_name == "get_flight_status":
            # Try to recover common cases even if the model returned an empty object.
            text = user_message
            surname_stopwords = {
                "где",
                "мой",
                "моя",
                "мое",
                "мои",
                "рейс",
                "статус",
                "покажи",
                "найди",
                "please",
                "flight",
                "status",
                "по",
                "номер",
                "номеру",
                "фамилия",
                "фамилию",
                "фамилией",
                "фамилии",
                "пассажир",
                "пассажира",
                "это",
            }
            flight_match = re.search(r"\b([A-Za-zА-Яа-яЁё]{2,3}\s?\d{1,4})\b", text)
            if flight_match and "flight_number" not in extracted:
                flight_number = flight_match.group(1).replace(" ", "").upper()
                flight_number = (
                    flight_number
                    .replace("СУ", "SU")
                    .replace("АЭ", "AE")
                )
                extracted["flight_number"] = flight_number
                # Model sometimes puts airline code into last_name (e.g. "SU" from "SU123").
                if isinstance(extracted.get("last_name"), str):
                    raw_last_name = extracted["last_name"].strip().upper()
                    if raw_last_name and raw_last_name == re.sub(r"\d+", "", flight_number):
                        extracted.pop("last_name", None)

            if "last_name" not in extracted and "flight_number" not in extracted:
                # Explicit "surname" patterns from user text.
                surname_patterns = [
                    r"\bфамили(?:я|ю|ей|и)\s*(?:[:\-]\s*)?([A-Za-zА-Яа-яЁё-]{2,})\b",
                    r"\b([A-Za-zА-Яа-яЁё-]{2,})\b(?:\s|,\s*)(?:это\s+)?(?:моя\s+)?фамили(?:я|ю|ей|и)\b",
                    r"\b(?:моя\s+)?фамили(?:я|ю|ей|и)\s*(?:[:\-]\s*)?([A-Za-zА-Яа-яЁё-]{2,})\b",
                ]
                for pattern in surname_patterns:
                    match = re.search(pattern, text, flags=re.IGNORECASE)
                    if not match:
                        continue
                    candidate = str(match.group(1) or "").strip()
                    if candidate and candidate.lower() not in surname_stopwords:
                        extracted["last_name"] = candidate
                        break

            if "last_name" not in extracted and "flight_number" not in extracted:
                words = re.findall(r"[A-Za-zА-Яа-яЁё]{2,}", text)
                candidates = [w for w in words if w.lower() not in surname_stopwords]
                if len(candidates) == 1:
                    extracted["last_name"] = candidates[0]

            if "flight_number" not in extracted and "last_name" not in extracted:
                missing = ["flight_number_or_last_name"]
                prompt = (
                    "Укажите номер рейса (например, SU123) или фамилию пассажира."
                )
            else:
                missing = []
                prompt = None

        elif tool_name == "search_airports_nearby":
            pos = _latest_tool_result("get_current_position") or {}
            pos_data = pos.get("data") if isinstance(pos.get("data"), dict) else {}

            # Backward-compatible normalization if model emits old keys.
            if "city" not in extracted and isinstance(pos_data.get("city"), str) and pos_data.get("city").strip():
                extracted["city"] = pos_data.get("city").strip()
            if "radius_km" not in extracted:
                extracted["radius_km"] = 50

            city_ok = isinstance(extracted.get("city"), str) and extracted["city"].strip()
            radius = _to_float(extracted.get("radius_km"))
            if radius is None:
                extracted["radius_km"] = 50
            else:
                extracted["radius_km"] = radius

            if not city_ok:
                missing = ["city"]
                prompt = "Не удалось определить город. Укажите город, рядом с которым нужно найти аэропорт."
            else:
                missing = []
                prompt = None

        elif tool_name == "build_route":
            # Normalize legacy key names if model uses old workflow schema names.
            key_aliases = {
                "from_latitude": "from_lat",
                "from_longitude": "from_lon",
                "to_latitude": "to_lat",
                "to_longitude": "to_lon",
            }
            for old_key, new_key in key_aliases.items():
                if new_key not in extracted and old_key in extracted:
                    extracted[new_key] = extracted.get(old_key)

            pos = _latest_tool_result("get_current_position") or {}
            pos_data = pos.get("data") if isinstance(pos.get("data"), dict) else {}
            airports = _latest_tool_result("search_airports_nearby") or {}
            airports_data = airports.get("data") if isinstance(airports.get("data"), dict) else {}
            airports_list = airports_data.get("airports") if isinstance(airports_data.get("airports"), list) else []
            first_airport = airports_list[0] if airports_list and isinstance(airports_list[0], dict) else {}

            if "from_lat" not in extracted and _to_float(pos_data.get("lat")) is not None:
                extracted["from_lat"] = _to_float(pos_data.get("lat"))
            if "from_lon" not in extracted and _to_float(pos_data.get("lon")) is not None:
                extracted["from_lon"] = _to_float(pos_data.get("lon"))
            if "to_lat" not in extracted and _to_float(first_airport.get("lat")) is not None:
                extracted["to_lat"] = _to_float(first_airport.get("lat"))
            if "to_lon" not in extracted and _to_float(first_airport.get("lon")) is not None:
                extracted["to_lon"] = _to_float(first_airport.get("lon"))

            required = ["from_lat", "from_lon", "to_lat", "to_lon"]
            missing_required = [k for k in required if _to_float(extracted.get(k)) is None]
            if missing_required:
                missing = missing_required
                prompt = (
                    "Не удалось собрать координаты для маршрута. Уточните пункт отправления или выберите аэропорт."
                )
            else:
                for k in required:
                    extracted[k] = _to_float(extracted.get(k))
                missing = []
                prompt = None

        return ToolParamsData(extracted=extracted, missing=missing, prompt=prompt)

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
        mode_hint = self._mode_instruction_ru(req.mode)
        system = (
            "Ты внутренний сервис LLM. Твоя задача — вернуть ТОЛЬКО один JSON-объект.\n"
            "Не используй markdown, не добавляй пояснения, не добавляй лишние ключи.\n"
            f"Режим: {req.mode}\n"
            f"Инструкция режима: {mode_hint}\n"
            "Проверь соответствие JSON указанной схеме. Если формат нарушен — исправь и верни только валидный JSON.\n"
            f"JSON Schema:\n{json.dumps(schema_json, ensure_ascii=False)}"
        )
        user = json.dumps(req.input or {}, ensure_ascii=False)

        options = dict(req.constraints or {})
        options.setdefault("temperature", 0.0)
        max_tokens = int(options.pop("max_tokens", self.default_max_tokens) or self.default_max_tokens)

        model = options.pop("model", None) or (self.llm_local_model if self._use_local else self.llm_remote_model)

        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]

        started_at = time.monotonic()
        logger.info(
            "infer_json start mode=%s request_id=%s session_id=%s provider=%s model=%s",
            req.mode,
            str(req.request_id),
            str(req.session_id) if req.session_id else "<none>",
            "local" if self._use_local else "remote",
            str(model),
        )
        try:
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
        except Exception:
            duration_ms = int((time.monotonic() - started_at) * 1000)
            logger.exception(
                "infer_json failed mode=%s request_id=%s session_id=%s duration_ms=%s",
                req.mode,
                str(req.request_id),
                str(req.session_id) if req.session_id else "<none>",
                duration_ms,
            )
            raise
        duration_ms = int((time.monotonic() - started_at) * 1000)
        logger.info(
            "infer_json done mode=%s request_id=%s duration_ms=%s effective_model=%s provider=%s",
            req.mode,
            str(req.request_id),
            duration_ms,
            str(result.get("model") or model),
            str(result.get("provider") or ("local" if self._use_local else "remote")),
        )

        self._set_inference_meta(
            str(req.request_id),
            {
                "mode": req.mode,
                "configured_model": self._configured_model(),
                "effective_model": str(result.get("model") or model),
                "provider": str(result.get("provider") or ("local" if self._use_local else "remote")),
            },
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
