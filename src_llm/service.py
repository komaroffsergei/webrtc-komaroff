import json
import logging
from pathlib import Path
from typing import Any, List, Dict

from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

import ollama
from nats.aio.msg import Msg

from src_llm.settings import STACK_SERVICE_NAME
from src_llm.utils.base_service import BaseService
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
        ollama_model: str,
        system_prompt_file: str,
        max_output_tokens: int,
        default_max_tokens: int,
        tools_manifest_file: str,
    ) -> None:
        super().__init__(
            service_name=service_name,
            nats_url=nats_url,
            llm_subject=llm_subject,
            events_subject=events_subject,
        )
        self.ollama_url = ollama_url
        self.ollama_model = ollama_model
        self.system_prompt_file = system_prompt_file
        self.max_output_tokens = int(max_output_tokens)
        self.default_max_tokens = int(default_max_tokens)
        self.tools = load_tools_from_manifest(tools_manifest_file)

        self.ollama = ollama.Client(host=ollama_url)

    async def on_run(self) -> None:
        await self._nats_logger.info(
            f"{STACK_SERVICE_NAME} service connected (ollama_url={self.ollama_url})"
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

    # def _call_ollama(
    #     self,
    #     *,
    #     messages: List[Dict[str, Any]],
    #     max_tokens: int,
    # ) -> Dict[str, Any]:
    #     response = self.ollama.chat(
    #         model=self.ollama_model,
    #         messages=messages,
    #         tools=self.tools or None,
    #         options={
    #             "num_predict": max_tokens,
    #         },
    #         stream=False,
    #     )
    #     return response.get("message", {})



    def _call_ollama(
        self,
        *,
        messages: List[Dict[str, Any]],
        max_tokens: int,
    ) -> Dict[str, Any]:
        # body = {
        #     "model": self.ollama_model,
        #     "prompt": messages[0].get('content'),
        #     "num_predict": max_tokens,
        #     "stream": False,
        # }
        #
        # data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        # req = Request(
        #     f"{self.ollama_url}/api/generate",
        #     data=data,
        #     headers={"Content-Type": "application/json"},
        #     method="POST",
        # )
        #
        # try:
        #     with urlopen(req, timeout=120) as resp:
        #         resp_body = resp.read().decode("utf-8", errors="replace")
        #         payload = json.loads(resp_body)
        # except HTTPError as exc:
        #     logger.error("OLLAMA HTTP error: %s", exc)
        #     raise
        # except URLError as exc:
        #     logger.error("OLLAMA URL error: %s", exc)
        #     raise
        # except Exception as exc:
        #     logger.error("OLLAMA request failed: %s", exc, exc_info=True)
        #     raise
        #
        # result = payload.get("response") or ""
        #
        #
        # logger.info("LLM response length=%d", len(result))
        # return result



        response = self.ollama.chat(
            model=self.ollama_model,
            messages=messages,
            tools=self.tools or None,
            options={
                "num_predict": max_tokens,
            },
            stream=False,
        )
        return response.get("message", {})




    # def on_message(self, msg: Msg) -> dict[str, Any]:
    #     # сюда приходят JSON-байты от src_core
    #     try:
    #         payload = json.loads(msg.data.decode("utf-8"))
    #     except Exception as exc:
    #         logger.error("Invalid JSON payload from NATS: %s", exc)
    #         return {"error": "invalid_json", "details": str(exc)}
    #
    #     text = (payload.get("text") or "").strip()
    #     if not text:
    #         return {"error": "empty_text"}
    #
    #     max_tokens_raw = payload.get("max_tokens")
    #     if max_tokens_raw is not None:
    #         try:
    #             max_tokens = int(max_tokens_raw)
    #         except Exception:
    #             max_tokens = self.default_max_tokens
    #     else:
    #         max_tokens = self.default_max_tokens
    #
    #     max_tokens = min(max_tokens, self.max_output_tokens)
    #
    #     system_prompt = self._get_system_prompt()
    #     prompt = (
    #         f"<|system|>\n{system_prompt}<|end|>\n"
    #         f"<|user|>\n{text}\n<|end|>\n"
    #     )
    #
    #     try:
    #         result = self._call_ollama(prompt, max_tokens)
    #     except Exception as exc:
    #         return {"error": "ollama_error", "details": str(exc)}
    #
    #     # это будет лежать в message["output"] на стороне BaseService
    #     return {"text": result}

    def on_message(self, msg: Msg) -> dict[str, Any]:
        payload = json.loads(msg.data.decode("utf-8"))

        messages = payload["messages"]
        max_tokens = min(
            int(payload.get("max_tokens", self.default_max_tokens)),
            self.max_output_tokens,
        )

        # text = (payload.get("text") or "").strip()
        # system_prompt = self._get_system_prompt()
        # prompt = (
        #     f"<|system|>\n{system_prompt}<|end|>\n"
        #     f"<|user|>\n{text}\n<|end|>\n"
        # )
        #
        # try:
        #     result = self._call_ollama(prompt, max_tokens)
        # except Exception as exc:
        #     return {"error": "ollama_error", "details": str(exc)}


        system_prompt = self._get_system_prompt()
        if system_prompt and not any(m["role"] == "system" for m in messages):
            messages = [{"role": "system", "content": system_prompt}, *messages]
        try:
            result = self._call_ollama(messages=messages, max_tokens=max_tokens)
        except Exception as exc:
            return {"error": "ollama_error", "details": str(exc)}


        # return result

        return {
            "role": result.get("role"),
            "content": result.get("content"),
            "tool_calls": result.get("tool_calls"),
            "tool_name": result.get("tool_name"),
        }
