import json


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


# -----------------------------
# LOGGING HELPERS
# -----------------------------

def log(title: str, data=None):
    print(f"\n=== {title} ===")
    if data is not None:
        if isinstance(data, (dict, list)):
            print(json.dumps(data, ensure_ascii=False, indent=2))
        else:
            print(data)