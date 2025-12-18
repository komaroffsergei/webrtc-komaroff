import os
from langchain_ollama import OllamaLLM

# === Конфигурация через окружение ===
# Пример:
# export OLLAMA_BASE_URL=http://192.168.2.108:11435
# export OLLAMA_MODEL=qwen2.5:7b

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://192.168.2.108:11435")
MODEL_NAME = os.getenv("OLLAMA_MODEL", "qwen2.5:7b")

os.environ["OLLAMA_BASE_URL"] = OLLAMA_BASE_URL

# === LLM ===
llm = OllamaLLM(
    model=MODEL_NAME,
    temperature=0.0,
    base_url=OLLAMA_BASE_URL,
)


def plan_steps(query: str) -> str:
    prompt = f"""
Ты MCP-агент для пилота.
Твоя задача — понять запрос и кратко описать логические шаги решения.

Запрос:
{query}

Верни нумерованный план шагов.
"""
    return llm.invoke(prompt)
