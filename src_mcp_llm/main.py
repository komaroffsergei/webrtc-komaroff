import os
from fastapi import FastAPI
from pydantic import BaseModel
from llama_cpp import Llama
from dotenv import load_dotenv
import uvicorn

# Грузим окружение
load_dotenv()

MODEL_PATH = os.getenv("MODEL_PATH", "model/Phi-3-mini-4k-instruct-q4.gguf")
CTX_SIZE = int(os.getenv("CTX_SIZE", "4096"))
THREADS = int(os.getenv("THREADS", "4"))
HOST = os.getenv("LLM_HOST", "127.0.0.1")
PORT = int(os.getenv("LLM_PORT", "6007"))

# Загружаем модель (при старте файла)
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
    output = llm(
        req.prompt,
        max_tokens=req.max_tokens,
        temperature=0.3,
        stop=["</s>", "###"]
    )
    text = output["choices"][0]["text"]
    return {"text": text.strip()}

# Запуск HTTP-сервера при прямом вызове файла
if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=HOST,
        port=PORT,
        reload=False
    )
