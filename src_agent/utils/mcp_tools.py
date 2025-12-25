import inspect
from typing import get_origin, get_args, List, Dict, Any, get_type_hints, Literal, TypedDict
class AgentRegistry(TypedDict, total=False):
    fn: Any
    schema: Dict[str, Any]
    provides: list[str] | None
    consumes: list[str] | None
    client_handler: str | None

REGISTRY: Dict[str, AgentRegistry] = {}
AgentErrorStatus = Literal[
    "TOOLS_EXCEPTION",
    "LLM_EXCEPTION",
    "MAX_STEPS_EXCEEDED",
    "UNSUPPORTED_REQUEST",
]

AGentClientCommands = Literal[
    "SHOW_ERROR_MESSAGE",
    "SET_POSITION",
    "SHOW_AIRPORTS",
    "BUILD_ROUTE",
] | str


class AgentError(TypedDict, total=False):
    type: AgentErrorStatus
    message: str
class AgentArtifacts(TypedDict, total=False):
    last: str
    all: List[str]
    payload: Dict[str, Any]
    # result: Any

class AgentClientHandler(TypedDict, total=False):
    command: AGentClientCommands | None
    artifacts: AgentArtifacts

class AgentResponse(TypedDict, total=False):
    success: bool
    data: Dict[str, Any]
    result: Any
    error: AgentError
    client_handler: AgentClientHandler | None




def mcp_tool(
    name: str | None = None,
    description: str | None = None,
    provides: list[str] | None = None,
    consumes: list[str] | None = None,
    parameters: dict[str, str] | None = None,
    client_handler: str | None = None,
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

        reg:AgentRegistry = {
            "fn": fn,
            "schema": build_schema(
                fn,
                tool_name,
                full_description,
                param_desc=parameters,
            ),
            "provides": prov,
            "consumes": cons,
            "client_handler": client_handler,
        }
        REGISTRY[tool_name] = reg

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

def build_tool_vocabulary() -> set[str]:
    """
    Строит словарь допустимых доменов/терминов на основе
    description всех зарегистрированных tools.

    Используется для pre-validation пользовательских запросов.
    """
    vocab: set[str] = set()

    for entry in REGISTRY.values():
        schema = entry.get("schema", {})
        fn = schema.get("function", {})
        desc = fn.get("description", "")

        if not desc:
            continue

        # примитивная токенизация, но стабильная
        for token in desc.lower().replace("\n", " ").split():
            # отсекаем мусор
            if len(token) < 3:
                continue
            vocab.add(token)

    return vocab


def check_prompt_by_vocabulary(prompt: str, vocab) -> bool:
    words = prompt.lower().split()
    return any(w in vocab for w in words)