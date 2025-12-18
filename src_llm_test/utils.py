import inspect
import json
from typing import re


def normalize_tool_content(value) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False)


def normalize_tool_calls(tool_calls):
    if not tool_calls:
        return None

    normalized = []
    for call in tool_calls:
        try:
            normalized.append({
                "name": call["function"]["name"]
                if isinstance(call, dict)
                else call.function.name,
                "arguments": call["function"]["arguments"]
                if isinstance(call, dict)
                else call.function.arguments,
            })
        except Exception:
            normalized.append(str(call))

    return normalized


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
                    # вытаскиваем первое число из строки
                    match = re.search(r"-?\d+(\.\d+)?", value)
                    if not match:
                        raise ValueError(f"No numeric value in '{value}'")
                    value = match.group(0)

                normalized[name] = ann(value)

            elif ann is bool:
                if isinstance(value, str):
                    normalized[name] = value.lower() in ("1", "true", "yes", "y")
                else:
                    normalized[name] = bool(value)

            elif ann is str:
                normalized[name] = str(value)

            else:
                normalized[name] = value

        except Exception as e:
            raise ValueError(
                f"Invalid value for '{name}': {value} ({e})"
            )

    return normalized



def log(title: str, data=None):
    print(f"\n=== {title} ===")
    if data is not None:
        if isinstance(data, (dict, list)):
            print(json.dumps(data, ensure_ascii=False, indent=2))
        else:
            print(data)

def log_step(step: int):
    print(f"\n==================== STEP {step} ====================")


def log_model_decision(content, tool_calls):
    print("\n--- MODEL DECISION ---")
    if content:
        print("Thinking:", content)
        print("Text:", content)
    if tool_calls:
        print("Tool calls:")
        print(json.dumps(tool_calls, ensure_ascii=False, indent=2))
    else:
        print("No tool calls")


def log_tool_call(name, args):
    print(f"\n>>> TOOL CALL: {name}")
    print(json.dumps(args, ensure_ascii=False, indent=2))


def log_tool_result(name, result):
    print(f"\n<<< TOOL RESULT: {name}")
    print(json.dumps(result, ensure_ascii=False, indent=2))


def log_final_answer(answer):
    print("\n==================== FINAL ANSWER ====================")
    print(answer)
