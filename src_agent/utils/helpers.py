import inspect
import json
import re
from typing import Dict, Any, List

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