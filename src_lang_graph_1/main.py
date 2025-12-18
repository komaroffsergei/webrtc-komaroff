from typing import Any

from src_lang_graph_1.graph import build_graph
from src_lang_graph_1.state import AgentState

EXAMPLES = [
    "Найди аэропорты в радиусе 100 км",
    "Найди аэропорты в радиусе 30 км со свободными ВПП",
    "Найди аэропорты в радиусе 1000 км у которых ВПП меньше 2 км",
    "Построй маршрут от моей позиции до ближайшего аэропорта",
    "Построй маршрут между двумя ближайшими аэропортами",
]


def get_field(result: Any, field: str):
    if hasattr(result, field):
        return getattr(result, field)
    if isinstance(result, dict):
        return result.get(field)
    return None


def run(app, query: str) -> None:
    state = AgentState(user_query=query)
    result = app.invoke(state)

    final_answer = get_field(result, "final_answer")
    plan = get_field(result, "plan")

    print(f"\nЗапрос: {query}")
    if plan:
        print("План:")
        print(plan)
    print("Ответ:")
    print(final_answer or "Нет ответа")


if __name__ == "__main__":
    app = build_graph()

    for example in EXAMPLES:
        run(app, example)
