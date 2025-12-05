import asyncio
from typing import Optional, Any

import nats
from nats.aio.msg import Msg

from src_llm.settings import STACK_SERVICE_NAME
from src_llm.utils.base_service import BaseService


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
            default_max_tokens: int
    ) -> None:
        super().__init__(
            service_name=service_name,
            nats_url=nats_url,
            frames_subject=frames_subject,
            logs_subject=logs_subject,
        )
        self.ollama_url = ollama_url,
        self.ollama_model = ollama_model,
        self.system_prompt_file = system_prompt_file,
        self.system_prompt = system_prompt,
        self.max_output_tokens = max_output_tokens,
        self.default_max_tokens = default_max_tokens

    async def on_run(self) -> None:
        await self._nats_logger.info(f"{STACK_SERVICE_NAME} service connected (on_run{self.ollama_url})")

    def on_message(self, msg: Msg) -> dict[str, bytes | Any]:
        return {"data": msg.data, "error": f"Hi from {self._service_name}"}


    # async def generate(self, msg: Msg) -> None:
# async def generate(payload: dict = Body(...)):
#     text = (payload.get("text") or "").strip()
#     max_tokens = (payload.get("max_tokens") or MAX_OUTPUT_TOKENS)
#     prompt = (
#         f"<|system|>\n{SYSTEM_PROMPT}<|end|>\n"
#         f"<|user|>\n{text}\n<|end|>\n"
#     )
#
#     req = {
#         "model": OLLAMA_MODEL,
#         "prompt": prompt,
#         "num_predict": max_tokens,
#         "stream": False
#     }
#
#     async with httpx.AsyncClient(timeout=120) as client:
#         r = await client.post(f"{OLLAMA_URL}/api/generate", json=req)
#         r.raise_for_status()
#         data = r.json()
#         result = data.get("response")
#
#         logger.info(result, name="llm.response")
#         return {"text": result}
