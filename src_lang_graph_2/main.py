# main.py
from src_lang_graph_2.agent import run_agent

EXAMPLES = [
    "Найди аэропорты в радиусе 100 км",
    "Найди аэропорты в радиусе 30 км со свободными ВПП",
]

if __name__ == "__main__":
    for q in EXAMPLES:
        print("\n==============================")
        print("QUERY:", q)
        artifacts = run_agent(q)
        print("RESULT:", artifacts)
