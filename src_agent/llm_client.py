import json
import logging

from src_agent.settings import STACK_SERVICE_NAME
from src_agent.utils.extract_json_from_text import extract_json_from_text

logger = logging.getLogger("agent.llm_client")


class LLMClient:
    def __init__(self, nc, llm_subject: str):
        self.nc = nc
        self.llm_subject = llm_subject  # ← nats.src_llm.user123


    async def call_llm(self, text: str) -> dict:
        request_payload = {
            "service": STACK_SERVICE_NAME,
            "text": text,
        }

        try:
            msg = await self.nc.request(
                self.llm_subject,
                json.dumps(request_payload, ensure_ascii=False).encode("utf-8"),
                timeout=30.0,
            )
            payload = json.loads(msg.data.decode("utf-8"))
        except Exception as e:
            logger.error("LLM request failed: %s", e)
            return {"raw": f"LLM request error: {e}", "parsed": None}

        # Обработка ответа от LLM сервиса
        raw = None
        if isinstance(payload, dict):
            if "text" in payload:
                raw = payload.get("text")
            elif isinstance(payload.get("output"), dict) and "text" in payload["output"]:
                raw = payload["output"]["text"]

        if raw is None:
            raw = json.dumps(payload, ensure_ascii=False)

        parsed = None
        try:
            parsed = extract_json_from_text(raw)
        except Exception as e:
            logger.error("Failed to parse JSON from LLM text: %s", e)

        return {
            "raw": raw,
            "parsed": parsed,
        }

# class LLMClient:
#     def __init__(self, nc):
#         self.nc = nc
#
    # async def call_llm(self, text: str) -> dict:
    #     request_payload = {
    #         "service": STACK_SERVICE_NAME,
    #         "text": text,
    #     }
    #
    #     try:
    #         msg = await self.nc.request(
    #             NATS_LLM_SUBJECT,
    #             json.dumps(request_payload, ensure_ascii=False).encode("utf-8"),
    #             timeout=60.0,
    #         )
    #         payload = json.loads(msg.data.decode("utf-8"))
    #     except Exception as e:
    #         logger.error("LLM request failed: %s", e)
    #         return {"raw": f"LLM request error: {e}", "parsed": None}
    #
    #     # Обработка ответа от LLM сервиса
    #     raw = None
    #     if isinstance(payload, dict):
    #         if "text" in payload:
    #             raw = payload.get("text")
    #         elif isinstance(payload.get("output"), dict) and "text" in payload["output"]:
    #             raw = payload["output"]["text"]
    #
    #     if raw is None:
    #         raw = json.dumps(payload, ensure_ascii=False)
    #
    #     parsed = None
    #     try:
    #         parsed = extract_json_from_text(raw)
    #     except Exception as e:
    #         logger.error("Failed to parse JSON from LLM text: %s", e)
    #
    #     return {
    #         "raw": raw,
    #         "parsed": parsed,
    #     }