import os
from typing import Dict, Any, List

from langchain_core.messages import HumanMessage, ToolMessage, SystemMessage
from langchain_ollama import ChatOllama

from src_lang_graph_2.tools import (
    get_current_position,
    search_airports,
    filter_airports_with_free_runways,
)



OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://192.168.2.108:11435")
MODEL_NAME = os.getenv("OLLAMA_MODEL", "qwen2.5:7b")

os.environ["OLLAMA_BASE_URL"] = OLLAMA_BASE_URL


SYSTEM_RULES = """
Ты агент, который решает задачи ТОЛЬКО через инструменты.

ЖЁСТКИЕ ПРАВИЛА:
- Если запрос содержит слова: "найди", "аэропорт", "в радиусе", "ВПП", "маршрут"
  ты ОБЯЗАН вызвать инструменты.
- Запрещено задавать вопросы пользователю.
- Запрещено отвечать текстом, пока не использованы инструменты.
- Если координаты не указаны — используй get_current_position.
"""

llm = ChatOllama(
    model=MODEL_NAME,
    temperature=0.0,
    base_url=OLLAMA_BASE_URL,
)

TOOLS = [
    get_current_position,
    search_airports,
    filter_airports_with_free_runways,
]
TOOL_BY_NAME = {t.name: t for t in TOOLS}
llm = llm.bind_tools(TOOLS)


def run_agent(query: str) -> Dict[str, Any]:
    messages: List[Any] = [
        SystemMessage(content=SYSTEM_RULES),
        HumanMessage(content=query)
    ]
    artifacts: Dict[str, Any] = {}

    for step in range(10):
        print(f"\n--- STEP {step + 1} ---")
        print("[STATE] artifacts:", artifacts)

        ai_msg = llm.invoke(messages)
        print("[LLM]:", ai_msg)

        # --- если модель решила вызвать инструмент ---
        if ai_msg.tool_calls:
            for call in ai_msg.tool_calls:
                name = call["name"]
                args = call["args"]

                print(f"[AGENT] tool_call: {name} {args}")

                # если модель забыла координаты — ДОПОЛНЯЕМ
                # if name == "search_airports":
                #     if "lat" not in args or "lon" not in args:
                #         pos = artifacts.get("position")
                #         if not pos:
                #             pos = get_current_position.invoke({})
                #             artifacts["position"] = pos
                #         args["lat"] = pos["lat"]
                #         args["lon"] = pos["lon"]

                tool = TOOL_BY_NAME[name]
                result = tool.invoke(args)

                # сохраняем
                if name == "get_current_position":
                    artifacts["position"] = result
                elif name == "search_airports":
                    artifacts["airports"] = result
                elif name == "filter_airports_with_free_runways":
                    artifacts["airports"] = result

                messages.append(
                    ToolMessage(
                        tool_call_id=call["id"],
                        content=str(result),
                    )
                )
            continue

        # --- если нет tool_calls — считаем, что всё ---
        print("[AGENT] finished")
        return artifacts

    raise RuntimeError("Agent did not finish")
