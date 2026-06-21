"""Memory tool — Persistent memory across sessions.

Memory is stored in ~/.wolf/memory/MEMORY.md (agent notes) and USER.md (user profile).
"""

import os
import re
import logging
from pathlib import Path
from typing import Any, Dict
from wolf.tools.registry import registry

logger = logging.getLogger(__name__)

MEMORY_DIR = Path.home() / ".wolf" / "memory"
MEMORY_FILE = MEMORY_DIR / "MEMORY.md"
USER_FILE = MEMORY_DIR / "USER.md"


def memory_handler(args: Dict[str, Any], context: Dict[str, Any] = None) -> Dict[str, Any]:
    """Manage persistent memory."""
    action = args.get("action", "read")
    target = args.get("target", "memory")  # "memory" or "user"
    content = args.get("content", "")
    old_text = args.get("old_text", "")

    target_file = USER_FILE if target == "user" else MEMORY_FILE

    if action == "read":
        if target_file.exists():
            return {"content": target_file.read_text(encoding="utf-8")}
        return {"content": ""}

    elif action == "add":
        MEMORY_DIR.mkdir(parents=True, exist_ok=True)
        existing = target_file.read_text(encoding="utf-8") if target_file.exists() else ""
        existing = existing.rstrip() + "\n- " + content.strip() + "\n"
        target_file.write_text(existing, encoding="utf-8")
        return {"success": True, "action": "added", "target": target}

    elif action == "replace":
        if not old_text:
            return {"error": "old_text required for replace action"}
        if not target_file.exists():
            return {"error": f"Target file not found: {target_file}"}
        text = target_file.read_text(encoding="utf-8")
        if old_text not in text:
            return {"error": f"old_text not found in {target}"}
        new_text = text.replace(old_text, content, 1)
        target_file.write_text(new_text, encoding="utf-8")
        return {"success": True, "action": "replaced", "target": target}

    elif action == "remove":
        if not old_text:
            return {"error": "old_text required for remove action"}
        if not target_file.exists():
            return {"error": f"Target file not found: {target_file}"}
        text = target_file.read_text(encoding="utf-8")
        if old_text not in text:
            return {"error": f"old_text not found in {target}"}
        new_text = text.replace(old_text, "", 1)
        target_file.write_text(new_text, encoding="utf-8")
        return {"success": True, "action": "removed", "target": target}

    else:
        return {"error": f"Unknown action: {action}. Use: read, add, replace, remove"}


registry.register(
    name="memory", toolset="memory",
    schema={
        "description": "Manage persistent memory across sessions. Save user preferences, environment facts, and lessons learned. Actions: read, add, replace, remove.",
        "parameters": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["read", "add", "replace", "remove"]},
                "target": {"type": "string", "enum": ["memory", "user"], "description": "memory=agent notes, user=user profile"},
                "content": {"type": "string", "description": "Content for add/replace"},
                "old_text": {"type": "string", "description": "Text to find for replace/remove"},
            },
            "required": ["action"],
        },
    },
    handler=memory_handler, emoji="🧠",
)
