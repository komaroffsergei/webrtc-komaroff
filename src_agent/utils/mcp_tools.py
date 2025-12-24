import inspect
from typing import get_type_hints

REGISTRY: dict = {}


def mcp_tool(
    name: str | None = None,
    description: str | None = None,
    provides: list[str] | None = None,
    consumes: list[str] | None = None,
    parameters: dict[str, str] | None = None,
):
    def wrapper(fn):
        tool_name = name or fn.__name__

        prov = provides or []
        cons = consumes or []

        desc_parts: list[str] = []

        if description:
            desc_parts.append(description.rstrip())

        if cons:
            desc_parts.append(
                "запрашивает артефакты: " + ", ".join(cons)
            )

        if prov:
            desc_parts.append(
                "заполняет артефакты: " + ", ".join(prov)
            )

        full_description = "\n".join(desc_parts)

        REGISTRY[tool_name] = {
            "fn": fn,
            "schema": build_schema(
                fn,
                tool_name,
                full_description,
                param_desc=parameters,
            ),
            "provides": prov,
            "consumes": cons,
        }
        return fn

    return wrapper



def build_schema(
    fn,
    name: str,
    description: str | None = None,
    param_desc: dict[str, str] | None = None,
):
    sig = inspect.signature(fn)
    hints = get_type_hints(fn)

    properties: dict[str, dict] = {}
    required: list[str] = []

    for param in sig.parameters.values():
        pname = param.name
        ptype = hints.get(pname)

        schema_prop = python_type_to_schema(ptype)

        if param_desc and pname in param_desc:
            schema_prop["description"] = param_desc[pname]

        properties[pname] = schema_prop

        if param.default is inspect._empty:
            required.append(pname)

    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description or "",
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required,
            },
        },
    }


from typing import get_origin, get_args, List, Dict, Any


def python_type_to_schema(py_type):
    if py_type is None:
        return {"type": "string"}

    origin = get_origin(py_type)
    args = get_args(py_type)

    if origin in (list, List):
        item = args[0] if args else Any
        return {"type": "array", "items": python_type_to_schema(item)}

    if origin in (dict, Dict):
        return {"type": "object"}

    if py_type is str:
        return {"type": "string"}
    if py_type is int:
        return {"type": "integer"}
    if py_type is float:
        return {"type": "number"}
    if py_type is bool:
        return {"type": "boolean"}

    return {"type": "string"}
