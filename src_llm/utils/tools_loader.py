import json
from pathlib import Path
from typing import Any, List, Dict


def load_tools_from_manifest(manifest_path: str) -> List[Dict[str, Any]]:
    path = Path(manifest_path)
    data = json.loads(path.read_text(encoding="utf-8"))

    tools = []
    for t in data.get("tools", []):
        tools.append({
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t.get("description", ""),
                "parameters": t.get("input_schema", {
                    "type": "object",
                    "properties": {}
                }),
            }
        })

    return tools
