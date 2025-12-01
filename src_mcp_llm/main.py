import json
import os
from fastapi import FastAPI
from pydantic import BaseModel, Field
from llama_cpp import Llama, LlamaGrammar
from textwrap import dedent
from dotenv import load_dotenv

load_dotenv()

MODEL_PATH = os.getenv("MODEL_PATH", "model/model.gguf")
N_CTX = int(os.getenv("N_CTX", "8192"))
N_THREADS = int(os.getenv("N_THREADS", "8"))
N_GPU_LAYERS = int(os.getenv("N_GPU_LAYERS", "35"))
MAX_OUTPUT_TOKENS = int(os.getenv("MAX_OUTPUT_TOKENS", "768"))
DEFAULT_MAX_TOKENS = int(os.getenv("DEFAULT_MAX_TOKENS", "512"))

with open("system_prompt.txt", "r", encoding="utf-8") as f:
    SYSTEM_PROMPT = f.read().strip()


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


# --------------------- LOAD MODEL ---------------------
llm = Llama(
    model_path=MODEL_PATH,
    n_ctx=N_CTX,
    n_threads=N_THREADS,
    n_gpu_layers=N_GPU_LAYERS,
    n_batch=512,
    use_mlock=True,
    use_mmap=True,
    verbose=False,
)

# # --------------------- GRAMMAR ---------------------
# GRAMMAR_TEXT = dedent(
#     r"""
# root ::= response
#
# response ::= "{" ws "\"thought\"" ws ":" ws string ws "," ws "\"history\"" ws ":" ws string ws "," ws "\"tool_calls\"" ws ":" ws call_array ws "," ws "\"final_result\"" ws ":" ws string ws "}"
#
# call_array ::= "[" ws (tool_call (ws "," ws tool_call)*)? ws "]"
#
# tool_call ::= "{" ws "\"thought\"" ws ":" ws string ws "," ws "\"call\"" ws ":" ws call_body ws "," ws "\"result\"" ws ":" ws value ws "}"
#
# call_body ::= "{" ws "\"tool\"" ws ":" ws string ws "," ws "\"parameters\"" ws ":" ws object ws "}"
#
# object ::= "{" ws (pair (ws "," ws pair)*)? ws "}"
#
# pair ::= string ws ":" ws value
#
# array ::= "[" ws (value (ws "," ws value)*)? ws "]"
#
# value ::= string | number | object | array | "null" | "true" | "false"
#
# string ::= "\"" chars "\""
#
# chars ::= ([^"\\] | "\\\\" | "\\\"" )*
#
# number ::= "-"? [0-9]+ ("." [0-9]+)?
#
# ws ::= [ \t\n\r]*
# """
# ).strip("\n") + "\n"
#
# JSON_GRAMMAR = LlamaGrammar.from_string(GRAMMAR_TEXT)

# --------------------- API ---------------------

app = FastAPI()


class Prompt(BaseModel):
    prompt: str = Field(..., description="Сформированный пользователем запрос/контекст")
    max_tokens: int | None = Field(default=None, ge=64, le=MAX_OUTPUT_TOKENS)


@app.post("/generate")
def generate(req: Prompt):
    prompt = (
        f"<|system|>\n{SYSTEM_PROMPT}<|end|>\n"
        f"<|user|>\n{req.prompt}<|end|>\n"
        f"<|assistant|>\n"
    )

    max_tokens = clamp_max_tokens(req.max_tokens)
    out = llm(
        prompt,
        max_tokens=max_tokens,
        temperature=0.0,
        top_p=0.1,
        top_k=1,
        # grammar=JSON_GRAMMAR,
        stop=["<|end|>", "<|user|>"],
    )

    text = out["choices"][0]["text"].strip()
    parsed = extract_json_from_text(text)
    response = {
        "raw": text,
        "parsed": parsed,
    }
    if parsed is None:
        response["error"] = "LLM returned an invalid JSON fragment"
    return response
