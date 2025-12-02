import asyncio
import json
import os
import sys
from pathlib import Path
from textwrap import dedent
from fastapi import FastAPI
from pydantic import BaseModel, Field
from llama_cpp import Llama, LlamaGrammar
from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from shared.sse import sse_log, SSEContext  # noqa: E402

load_dotenv()

MODEL_PATH = os.getenv("MODEL_PATH", "model/model.gguf")
N_CTX = int(os.getenv("N_CTX", "8192"))
N_THREADS = int(os.getenv("N_THREADS", max(1, os.cpu_count() - 1)))
N_GPU_LAYERS = int(os.getenv("N_GPU_LAYERS", "0"))
MAX_OUTPUT_TOKENS = int(os.getenv("MAX_OUTPUT_TOKENS", "4096"))
DEFAULT_MAX_TOKENS = int(os.getenv("DEFAULT_MAX_TOKENS", "4096"))

with open("system_prompt.txt", "r", encoding="utf-8") as f:
    SYSTEM_PROMPT = f.read().strip()

SSE_SERVICE_NAME = os.getenv("LLM_SERVICE_NAME", "src_mcp_llm")
SSE_CONTEXT = SSEContext(service_name=SSE_SERVICE_NAME)


def clamp_max_tokens(requested: int | None) -> int:
    if requested is None:
        return min(DEFAULT_MAX_TOKENS, MAX_OUTPUT_TOKENS)
    return max(64, min(requested, MAX_OUTPUT_TOKENS))


def extract_json_from_text(text: str):
    """
    Возвращает первый валидный JSON-объект из текста, если он присутствует.
    """
    start = text.find("{")
    if start == -1:
        return None

    in_string = False
    escaped = False
    depth = 0
    for idx in range(start, len(text)):
        ch = text[idx]
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
        else:
            if ch == '"':
                in_string = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    candidate = text[start : idx + 1]
                    try:
                        return json.loads(candidate)
                    except json.JSONDecodeError:
                        return None
    return None


llm = Llama(
    model_path=MODEL_PATH,
    n_ctx=N_CTX,
    n_threads=N_THREADS,
    n_gpu_layers=N_GPU_LAYERS,
    n_batch=512,
    use_mlock=False,
    use_mmap=True,
    verbose=False,
)


app = FastAPI()


class Prompt(BaseModel):
    summary: str = Field(
        default="",
        description="Короткая сводка истории, переданная агентом",
    )
    observations: list[str] = Field(
        default_factory=list,
        description="Список наблюдений с предыдущего шага",
    )
    user_request: str = Field(
        ...,
        description="Текущий запрос пользователя",
    )
    max_tokens: int | None = Field(default=None, ge=64, le=MAX_OUTPUT_TOKENS)


async def _log(message: str, level: str = "info", name: str | None = None):
    try:
        await sse_log(
            SSE_CONTEXT,
            message,
            level=level,
            service=SSE_SERVICE_NAME,
            name=name,
        )
    except Exception:
        pass


@app.post("/generate")
async def generate(req: Prompt):
    summary_text = req.summary.strip() or "История отсутствует. Это первый шаг."
    observations = [item.strip() for item in req.observations if isinstance(item, str) and item.strip()]
    if observations:
        obs_block = "\n".join(f"- {item}" for item in observations)
    else:
        obs_block = "нет новых наблюдений"
    user_text = req.user_request.strip()

    prompt = (
        f"<|system|>\n{SYSTEM_PROMPT}<|end|>\n"
        f"<|user|>\n"
        f"Summary:\n{summary_text}\n\n"
        f"Observations:\n{obs_block}\n\n"
        f"User request:\n{user_text}\n"
        f"<|end|>\n"
        f"<|assistant|>\n"
    )

    await _log(f"LLM request received (tokens<= {req.max_tokens or 'default'})", name="llm_request")
    max_tokens = clamp_max_tokens(req.max_tokens)
    loop = asyncio.get_running_loop()

    def _run_llm():
        return llm(
            prompt,
            max_tokens=max_tokens,
            temperature=0.0,
            top_p=0.1,
            top_k=1,
            # grammar=JSON_GRAMMAR,
            stop=["<|end|>", "<|user|>"],
        )

    try:
        out = await loop.run_in_executor(None, _run_llm)
    except Exception as exc:
        await _log(f"LLM call failed: {exc}", level="error", name="llm_failure")
        raise

    text = out["choices"][0]["text"].strip()
    parsed = extract_json_from_text(text)
    response = {
        "raw": text,
        "parsed": parsed,
    }
    if parsed is None:
        response["error"] = "LLM returned an invalid JSON fragment"
        await _log("LLM returned invalid JSON fragment", level="warning", name="llm_invalid_json")
    else:
        await _log("LLM response parsed successfully", level="success", name="llm_response")
    return response
