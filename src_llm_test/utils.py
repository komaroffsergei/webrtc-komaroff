import inspect
import json
import re
from src_llm_test.settings import DEBUG


def _p(msg: str):
    if DEBUG:
        print(msg)


def _j(obj):
    return json.dumps(obj, ensure_ascii=False, indent=2)


def log_user_query(text: str):
    _p(f"\n[DEBUG][USER]\n{text}")


def log_system_prompt():
    _p("[DEBUG][SYSTEM] system prompt sent")


def log_step(step: int):
    _p(f"\n[DEBUG][STEP {step}]")


def log_llm_response(content, tool_calls):
    if content:
        _p("[DEBUG][LLM][thinking]")
        _p(content.strip())

    if tool_calls:
        _p("[DEBUG][LLM][tool_calls]")
        _p(_j(tool_calls))


def log_tool_call(name: str, args: dict):
    _p(f"[DEBUG][TOOL CALL] {name}")
    _p(_j(args))


def log_tool_result(name: str, result):
    _p(f"[DEBUG][TOOL RESULT] {name}")
    _p(_j(result))


def log_error(err: Exception):
    _p("[DEBUG][ERROR]")
    _p(str(err))


def log_final_answer(answer: str):
    _p("\n[DEBUG][FINAL ANSWER]")
    _p(answer)


def log_stats(steps: int, total_time: float):
    _p(f"[DEBUG][STATS] steps={steps} time={total_time:.3f}s")


# -------- helpers --------

def normalize_tool_calls(tool_calls):
    if not tool_calls:
        return None

    out = []
    for c in tool_calls:
        out.append({
            "name": c["function"]["name"],
            "arguments": c["function"]["arguments"],
        })
    return out


def normalize_args(fn, args: dict) -> dict:
    sig = inspect.signature(fn)
    normalized = {}

    for name, param in sig.parameters.items():
        if name not in args:
            continue

        value = args[name]
        ann = param.annotation

        try:
            if ann in (int, float):
                if isinstance(value, str):
                    m = re.search(r"-?\d+(\.\d+)?", value)
                    if not m:
                        raise ValueError("no numeric value")
                    value = m.group(0)
                normalized[name] = ann(value)

            elif ann is bool:
                normalized[name] = str(value).lower() in ("1", "true", "yes")

            elif ann is str:
                normalized[name] = str(value)

            else:
                normalized[name] = value

        except Exception as e:
            raise ValueError(f"{name}={value} ({e})")

    return normalized
