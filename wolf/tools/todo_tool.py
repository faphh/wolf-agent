"""Todo tool — Task list management for current session."""

import logging
from typing import Any, Dict, List
from wolf.tools.registry import registry

logger = logging.getLogger(__name__)

# In-memory task list (per session)
_todos: List[Dict[str, Any]] = []


def todo_handler(args: Dict[str, Any], context: Dict[str, Any] = None) -> Dict[str, Any]:
    """Manage task list."""
    global _todos
    action = args.get("action", "read")

    if action == "read":
        return {"todos": _todos}

    elif action == "write":
        items = args.get("items", [])
        merge = args.get("merge", False)
        if not merge:
            _todos = items
        else:
            existing_ids = {t["id"] for t in _todos}
            for item in items:
                if item["id"] in existing_ids:
                    _todos = [item if t["id"] == item["id"] else t for t in _todos]
                else:
                    _todos.append(item)
        return {"todos": _todos}

    elif action == "update":
        item_id = args.get("id", "")
        updates = args.get("updates", {})
        for t in _todos:
            if t.get("id") == item_id:
                t.update(updates)
                return {"success": True, "item": t}
        return {"error": f"Todo item not found: {item_id}"}

    return {"error": f"Unknown action: {action}"}


registry.register(
    name="todo", toolset="task",
    schema={
        "description": "Manage task list. Actions: read (get current), write (set list), update (change item status).",
        "parameters": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["read", "write", "update"]},
                "items": {"type": "array", "description": "Todo items (for write)"},
                "merge": {"type": "boolean", "description": "Merge with existing (for write)", "default": False},
                "id": {"type": "string", "description": "Item ID (for update)"},
                "updates": {"type": "object", "description": "Fields to update (for update)"},
            },
            "required": ["action"],
        },
    },
    handler=todo_handler, emoji="📋",
)
