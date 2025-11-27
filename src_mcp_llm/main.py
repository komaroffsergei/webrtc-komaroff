import os
from fastapi import FastAPI
from pydantic import BaseModel
from llama_cpp import Llama
from dotenv import load_dotenv

load_dotenv()

MODEL_PATH = os.getenv("MODEL_PATH", "model/Phi-3-mini-4k-instruct-q4.gguf")
CTX_SIZE = int(os.getenv("CTX_SIZE", "4096"))
THREADS = int(os.getenv("THREADS", "4"))

with open("system_prompt.txt", "r") as f:
    SYSTEM_PROMPT = f.read().strip()

# Загружаем модель
llm = Llama(
    model_path=MODEL_PATH,
    n_ctx=CTX_SIZE,
    n_threads=THREADS,
    use_mmap=True,
    use_mlock=False,
    verbose=False
)


app = FastAPI()

class Prompt(BaseModel):
    prompt: str
    max_tokens: int | None = 256

@app.post("/generate")
def generate(req: Prompt):
    full_prompt = f"[SYSTEM]\n{SYSTEM_PROMPT}\n[/SYSTEM]\n\n{req.prompt}"

    output = llm(
        full_prompt,
        max_tokens=req.max_tokens,
        temperature=0.3,
        stop=["</s>", "###"]
    )

    text = output["choices"][0]["text"]
    return {"text": text.strip()}


# -------------------------
# ПРОГРЕВ МОДЕЛИ
# -------------------------
try:
    llm("Warmup", max_tokens=1)
except Exception:
    pass
# -------------------------
