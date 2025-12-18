import inspect
from typing import get_type_hints

REGISTRY = {}


def mcp_tool(
    name: str | None = None,
    description: str | None = None,
    provides: list[str] | None = None,
    consumes: list[str] | None = None,
    parameters: dict[str, str] | None = None,
):

    def wrapper(fn):
        tool_name = name or fn.__name__

        REGISTRY[tool_name] = {
            "fn": fn,
            "schema": build_schema(fn, tool_name, description),
            "provides": provides or [],
            "consumes": consumes or [],
        }
        return fn
    return wrapper


def build_schema(
    fn,
    name: str,
    description: str | None = None,
    param_desc: dict[str, str] | None = None,
):
    import inspect
    from typing import get_type_hints

    sig = inspect.signature(fn)
    hints = get_type_hints(fn)

    properties: dict[str, dict] = {}
    required: list[str] = []

    for param in sig.parameters.values():
        param_name = param.name
        param_type = hints.get(param_name)

        schema_prop = {
            "type": python_type_to_json(param_type)
        }

        if param_desc and param_name in param_desc:
            schema_prop["description"] = param_desc[param_name]

        properties[param_name] = schema_prop

        if param.default is inspect._empty:
            required.append(param_name)

    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description or (fn.__doc__ or ""),
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required,
            },
        },
    }




def python_type_to_json(tp):
    return {
        int: "number",
        float: "number",
        str: "string",
        bool: "boolean",
    }.get(tp, "string")
