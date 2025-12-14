from typing import Any


def to_json_safe(value: Any) -> Any:
    if value is None:
        return None

    if isinstance(value, (str, int, float, bool)):
        return value

    if isinstance(value, dict):
        return {str(k): to_json_safe(v) for k, v in value.items()}

    if isinstance(value, (list, tuple, set)):
        return [to_json_safe(v) for v in value]

    # dataclass / pydantic / SDK objects
    if hasattr(value, "__dict__"):
        return to_json_safe(vars(value))

    # datetime и подобное
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except Exception:
            pass

    # крайний случай — строка
    return str(value)