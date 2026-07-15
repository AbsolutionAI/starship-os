import json
from datetime import datetime, timezone


async def handle_tool(tool_name: str, arguments: dict, config: dict) -> dict:
    if tool_name == "greet":
        name = arguments.get("name", "")
        greeting = config.get("default_greeting", "Hello!")
        if name:
            return {"output": f"{greeting}, {name}!", "error": False}
        return {"output": greeting, "error": False}

    elif tool_name == "current_time":
        now = datetime.now(timezone.utc)
        return {"output": now.isoformat(), "timezone": "UTC", "error": False}

    return {"error": True, "message": f"Unknown tool: {tool_name}"}
