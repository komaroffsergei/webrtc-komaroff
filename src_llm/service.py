import json
import logging
from pathlib import Path
from typing import Any

from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

from nats.aio.msg import Msg

from src_llm.settings import STACK_SERVICE_NAME
from src_llm.utils.base_service import BaseService

logger = logging.getLogger(STACK_SERVICE_NAME)


class LLMService(BaseService):
    def __init__(
        self,
        *,
        service_name: str,
        nats_url: str,
        frames_subject: str,
        logs_subject: str,
        ollama_url: str,
        ollama_model: str,
        system_prompt_file: str,
        system_prompt: str,
        max_output_tokens: int,
        default_max_tokens: int,
    ) -> None:
        super().__init__(
            service_name=service_name,
            nats_url=nats_url,
            frames_subject=frames_subject,
            logs_subject=logs_subject,
        )
        # без запятых, нам тут не tuple нужны
        self.ollama_url = ollama_url
        self.ollama_model = ollama_model
        self.system_prompt_file = system_prompt_file
        self.system_prompt = system_prompt
        self.max_output_tokens = int(max_output_tokens)
        self.default_max_tokens = int(default_max_tokens)

    async def on_run(self) -> None:
        await self._nats_logger.info(
            f"{STACK_SERVICE_NAME} service connected (ollama_url={self.ollama_url})"
        )

    def _get_system_prompt(self) -> str:
        if self.system_prompt:
            return self.system_prompt

        if not self.system_prompt_file:
            return ""

        try:
            content = Path(self.system_prompt_file).read_text(encoding="utf-8").strip()
            return content
        except Exception as exc:
            logger.warning("Failed to read system prompt file %s: %s",
                           self.system_prompt_file, exc)
            return ""

    def _call_ollama(self, prompt: str, max_tokens: int) -> str:
        body = {
            "model": self.ollama_model,
            "prompt": prompt,
            "num_predict": max_tokens,
            "stream": False,
        }

        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        req = Request(
            f"{self.ollama_url}/api/generate",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urlopen(req, timeout=120) as resp:
                resp_body = resp.read().decode("utf-8", errors="replace")
                payload = json.loads(resp_body)
        except HTTPError as exc:
            logger.error("OLLAMA HTTP error: %s", exc)
            raise
        except URLError as exc:
            logger.error("OLLAMA URL error: %s", exc)
            raise
        except Exception as exc:
            logger.error("OLLAMA request failed: %s", exc, exc_info=True)
            raise

        result = payload.get("response") or ""
        logger.info("LLM response length=%d", len(result))
        return result

    def on_message(self, msg: Msg) -> dict[str, Any]:
        # сюда приходят JSON-байты от src_core
        try:
            payload = json.loads(msg.data.decode("utf-8"))
        except Exception as exc:
            logger.error("Invalid JSON payload from NATS: %s", exc)
            return {"error": "invalid_json", "details": str(exc)}

        text = (payload.get("text") or "").strip()
        if not text:
            return {"error": "empty_text"}

        max_tokens_raw = payload.get("max_tokens")
        if max_tokens_raw is not None:
            try:
                max_tokens = int(max_tokens_raw)
            except Exception:
                max_tokens = self.default_max_tokens
        else:
            max_tokens = self.default_max_tokens

        max_tokens = min(max_tokens, self.max_output_tokens)

        system_prompt = self._get_system_prompt()
        prompt = (
            f"<|system|>\n{system_prompt}<|end|>\n"
            f"<|user|>\n{text}\n<|end|>\n"
        )

        try:
            result = self._call_ollama(prompt, max_tokens)
        except Exception as exc:
            return {"error": "ollama_error", "details": str(exc)}

        # это будет лежать в message["output"] на стороне BaseService
        return {"text": result}
