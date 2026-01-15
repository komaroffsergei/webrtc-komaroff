import json
import logging
import threading
from pathlib import Path

import ollama
from nats.aio.msg import Msg

from src_llm.clients.local_chat import chat as local_chat
from src_llm.clients.ollama_chat import chat as ollama_chat
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

    def on_message(self, msg: Msg) -> dict:
        payload = json.loads(msg.data.decode("utf-8"))
        messages = payload.get("messages") or []
        tools = payload.get("tools")
        options = payload.get("options") or {}
        model = payload.get("model") or (self.llm_local_model if self._use_local else self.llm_remote_model)

        if self._use_local:
            with self._inference_lock:
                return local_chat(
                    self._ensure_local_model(),
                    model=model,
                    messages=messages,
                    tools=tools,
                    options=options,
                    max_tokens=self.default_max_tokens,
                )

        return ollama_chat(
            self._ollama,
            model=model,
            messages=messages,
            tools=tools,
            options=options,
            think=bool(payload.get("think", False)),
        )
