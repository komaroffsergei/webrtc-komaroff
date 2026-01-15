import json
import logging
import threading
from pathlib import Path
from typing import Any

import ollama
from nats.aio.msg import Msg

from src_llm.settings import STACK_SERVICE_NAME
from src_llm.utils.base_service import BaseService
from src_llm.utils.model_downloader import ensure_model_path
from src_llm.utils.tools_loader import load_tools_from_manifest

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
        system_prompt_file: str,
        max_output_tokens: int,
        default_max_tokens: int,
        tools_manifest_file: str,
        llm_mode: str,
        llm_models_dir: str,
        ollama_model_file: str,
        llm_context_size: int,
        llm_chat_format: str,
    ) -> None:
        super().__init__(
            service_name=service_name,
            nats_url=nats_url,
            llm_subject=llm_subject,
            events_subject=events_subject,
        )
        self.ollama_url = ollama_url
        self.llm_local_model = llm_local_model
        self.llm_remote_model = llm_remote_model
        self.system_prompt_file = system_prompt_file
        self.max_output_tokens = int(max_output_tokens)
        self.default_max_tokens = int(default_max_tokens)
        self.tools = load_tools_from_manifest(tools_manifest_file)
        self.llm_mode = (llm_mode or "remote").strip().lower()
        self.llm_models_dir = llm_models_dir
        self.ollama_model_file = (ollama_model_file or "").strip() or None
        self.llm_context_size = int(llm_context_size)
        self.llm_chat_format = (llm_chat_format or "").strip() or None
        self._use_local = self.llm_mode == "local"

        self._ollama = None if self._use_local else ollama.Client(host=ollama_url)
        self._local_model = None
        self._model_lock = threading.Lock()
        self._inference_lock = threading.Lock()

    async def on_run(self) -> None:
        await self._nats_logger.info(
            f"{STACK_SERVICE_NAME} service connected (mode={self.llm_mode})"
        )

    def _get_system_prompt(self) -> str:
        if not self.system_prompt_file:
            return ""

        try:
            content = Path(self.system_prompt_file).read_text(encoding="utf-8").strip()
            return content
        except Exception as exc:
            logger.warning("Failed to read system prompt file %s: %s",
                           self.system_prompt_file, exc)
            return ""

    def _ensure_local_model(self):
        if self._local_model:
            return self._local_model

        with self._model_lock:
            if self._local_model:
                return self._local_model

            model_id = self.llm_local_model
            model_path = ensure_model_path(
                model_id,
                self.llm_models_dir,
                self.ollama_model_file,
            )
            logger.info("Loading local model from %s", model_path)

            from llama_cpp import Llama

            init_kwargs = {
                "model_path": model_path,
                "n_ctx": self.llm_context_size,
            }
            if self.llm_chat_format:
                init_kwargs["chat_format"] = self.llm_chat_format

            try:
                self._local_model = Llama(**init_kwargs)
            except TypeError:
                init_kwargs.pop("chat_format", None)
                self._local_model = Llama(**init_kwargs)

        return self._local_model

    def _normalize_tool_calls(self, tool_calls: Any) -> Any:
        if not tool_calls:
            return tool_calls

        for call in tool_calls:
            function = call.get("function") or {}
            args = function.get("arguments")
            if isinstance(args, str):
                try:
                    function["arguments"] = json.loads(args)
                except json.JSONDecodeError:
                    function["arguments"] = {"_raw": args}
        return tool_calls

    def _ollama_chat(self, *, model: str, messages: list, tools: list, options: dict, think: bool) -> dict[str, Any]:
        if not self._ollama:
            return {"error": "ollama_error", "details": "Ollama client is not configured"}

        response = self._ollama.chat(
            model=model,
            messages=messages,
            tools=tools or [],
            options=options or {},
            think=think,
            stream=False,
        )
        message = response.get("message", {})
        message["tool_calls"] = self._normalize_tool_calls(message.get("tool_calls"))
        return {
            "message": message,
            "model": response.get("model", model),
            "provider": "ollama",
        }

    def _local_chat(self, *, model: str, messages: list, tools: list, options: dict) -> dict[str, Any]:
        llama = self._ensure_local_model()
        params = {
            "temperature": options.get("temperature", 0.0),
            "top_p": options.get("top_p"),
            "top_k": options.get("top_k"),
            "max_tokens": options.get("num_predict") or options.get("max_tokens") or self.default_max_tokens,
        }
        params = {k: v for k, v in params.items() if v is not None}

        with self._inference_lock:
            response = llama.create_chat_completion(
                messages=messages,
                tools=tools or [],
                **params,
            )

        choices = response.get("choices") or []
        message = choices[0].get("message", {}) if choices else {}
        message["tool_calls"] = self._normalize_tool_calls(message.get("tool_calls"))
        return {
            "message": message,
            "model": model,
            "provider": "local",
        }

    def on_message(self, msg: Msg) -> dict[str, Any]:
        try:
            payload = json.loads(msg.data.decode("utf-8"))
        except Exception as exc:
            return {"error": "invalid_payload", "details": str(exc)}

        messages = payload.get("messages")
        if not isinstance(messages, list):
            return {"error": "invalid_payload", "details": "messages must be a list"}

        system_prompt = self._get_system_prompt()
        if system_prompt and not any(m.get("role") == "system" for m in messages):
            messages = [{"role": "system", "content": system_prompt}, *messages]

        tools = payload.get("tools")
        if tools is None:
            tools = self.tools

        options = payload.get("options") or {}
        think = bool(payload.get("think", False))
        model = payload.get("model") or (self.llm_local_model if self._use_local else self.llm_remote_model)

        try:
            if self._use_local:
                return self._local_chat(model=model, messages=messages, tools=tools, options=options)
            return self._ollama_chat(
                model=model,
                messages=messages,
                tools=tools,
                options=options,
                think=think,
            )
        except Exception as exc:
            logger.exception("LLM request failed: %s", exc)
            return {"error": "llm_error", "details": str(exc)}
