import json
import os
from typing import Optional, Dict, Any

from fastapi import FastAPI
from pydantic import BaseModel
from llama_cpp import Llama, LlamaGrammar
from dotenv import load_dotenv

load_dotenv()

MODEL_PATH = os.getenv("MODEL_PATH", "model/Phi-3-mini-4k-instruct-q4.gguf")
CTX_SIZE = int(os.getenv("CTX_SIZE", "4096"))
THREADS = int(os.getenv("THREADS", "4"))
N_CTX = int(os.getenv("N_CTX", "8192"))
N_THREADS = int(os.getenv("N_THREADS", "8"))

with open("system_prompt.txt", "r") as f:
    SYSTEM_PROMPT = f.read().strip()

# Загружаем модель
llm = Llama(
    model_path=MODEL_PATH,
    n_ctx=N_CTX,
    n_threads=N_THREADS,
    n_batch=512,
    n_gpu_layers=35 if os.getenv("GPU", "0") != "0" else 0,
    use_mlock=True,
    use_mmap=True,
    verbose=False,
)


app = FastAPI()

class Prompt(BaseModel):
    prompt: str
    max_tokens: int | None = 256


def extract_json_from_text(text: str) -> Optional[Dict[str, Any]]:
    text = text.strip()
    start = text.find("{")
    if start == -1:
        return None

    # Обрезаем до последнего закрывающего }
    json_candidate = text[start:]
    depth = 0
    end = -1
    for i, char in enumerate(json_candidate):
        if char == '{':
            depth += 1
        elif char == '}':
            depth -= 1
            if depth == 0:
                end = i
                break

    if end == -1:
        return None

    try:
        data = json.loads(json_candidate[:end+1])
        # Проверяем, что это наш нужный формат
        if isinstance(data, dict) and "thought" in data and "tool_calls" in data and "answer" in data:
            return data
    except json.JSONDecodeError:
        pass
    return None

@app.post("/generate")
def generate(req: Prompt):
    # ←←← КЛЮЧЕВОЙ МОМЕНТ: используем чат-теги, даже в простом режиме
    full_prompt = f"<|system|>\n{SYSTEM_PROMPT}<|end|>\n<|user|>\n{req.prompt}<|end|>\n<|assistant|>\n"

    # ГРАММАТИКА, КОТОРАЯ ЗАСТАВЛЯЕТ ВСЕГДА ЗАКРЫВАТЬ СКОБКИ
    JSON_GRAMMAR = LlamaGrammar.from_string(
        r"""
        root   ::= object
        object ::= "{" ws "}" | "{" ws members ws "}"
        members ::= pair (ws "," ws members)?
        pair   ::= string ws ":" ws value
        value  ::= object | array | string | number | "true" | "false" | "null"
        array  ::= "[" ws "]" | "[" ws elements ws "]"
        elements ::= value (ws "," ws elements)?
        string ::= "\"" ( [^"\\] | "\\" (["\\/bfnrt] | "u" [0-9a-fA-F]{4}) )* "\""
        number ::= "-"? ( "0" | [1-9][0-9]* ) ( "." [0-9]+ )? ( [eE] [+-]? [0-9]+ )?
        ws     ::= [ \s*
        """
    )

    output = llm(
        full_prompt,
        max_tokens=req.max_tokens,
        temperature=0.0,
        top_p=0.1,
        top_k=1,
        repeat_penalty=1.1,
        stop=["<|end|>", "</s>", "<|user|>", "User:"],
        grammar=JSON_GRAMMAR,
        echo=False,
    )

    raw = output["choices"][0]["text"].strip()

    parsed = extract_json_from_text(raw)

    # ←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←
    # Если модель выдала мусор — принудительно возвращаем ошибку в нужном формате
    # ←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←
    if not parsed:
        parsed = {
            "thought": "Модель не смогла сформировать ответ в требуемом JSON-формате.",
            "tool_calls": [
                {
                    "thought": "Принудительно вызываем error_report из-за нарушения формата.",
                    "call": {"tool": "error_report", "parameters": {"reason": "invalid response format"}},
                    "result": None
                }
            ],
            "answer": "Модель не смогла сформировать ответ в требуемом JSON-формате."
        }

    return {
        "raw": raw,
        "parsed": parsed,
        "is_final": bool(parsed.get("answer", "").strip()),
        "pending_tools": [
            item["call"] for item in parsed.get("tool_calls", []) if item.get("result") is None
        ]
    }

# -------------------------
# ПРОГРЕВ МОДЕЛИ
# -------------------------
# try:
#     llm("Warmup", max_tokens=1)
# except Exception:
#     pass
# -------------------------
