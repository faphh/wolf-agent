"""Patch tool — Precise find-and-replace editing (Claude Code style).

Uses fuzzy matching to find the target string even with minor whitespace differences.
"""

import os
import difflib
import logging
from typing import Any, Dict, Optional
from wolf.tools.registry import registry

logger = logging.getLogger(__name__)


def _fuzzy_find(content: str, old_string: str) -> tuple:
    """Find old_string in content with fuzzy matching. Returns (start, end, score)."""
    # Exact match first
    idx = content.find(old_string)
    if idx >= 0:
        return (idx, idx + len(old_string), 1.0)

    # Try normalized whitespace matching
    def normalize(s):
        return " ".join(s.split())

    norm_old = normalize(old_string)
    lines = content.split("\n")

    best_score = 0
    best_start = -1
    best_end = -1

    old_lines = old_string.split("\n")
    window_size = len(old_lines)

    for i in range(len(lines) - window_size + 1):
        window = "\n".join(lines[i:i + window_size])
        norm_window = normalize(window)
        score = difflib.SequenceMatcher(None, norm_old, norm_window).ratio()
        if score > best_score:
            best_score = score
            best_start = sum(len(lines[j]) + 1 for j in range(i))
            best_end = best_start + len(window)

    if best_score >= 0.8:
        return (best_start, best_end, best_score)

    return (-1, -1, 0)


def patch_handler(args: Dict[str, Any], context: Dict[str, Any] = None) -> Dict[str, Any]:
    """Replace old_string with new_string in a file."""
    path = args.get("path", "")
    old_string = args.get("old_string", "")
    new_string = args.get("new_string", "")
    replace_all = args.get("replace_all", False)

    if not path:
        return {"error": "No path provided"}
    if not old_string:
        return {"error": "No old_string provided"}

    path = os.path.expanduser(path)
    if not os.path.exists(path):
        return {"error": f"File not found: {path}"}

    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()

        if replace_all:
            count = content.count(old_string)
            if count == 0:
                return {"error": f"old_string not found in {path}", "success": False}
            new_content = content.replace(old_string, new_string)
        else:
            start, end, score = _fuzzy_find(content, old_string)
            if start < 0:
                return {"error": f"old_string not found in {path} (best match score: {score:.2f})"}
            new_content = content[:start] + new_string + content[end:]
            count = 1

        with open(path, "w", encoding="utf-8") as f:
            f.write(new_content)

        # Generate diff preview
        diff = list(difflib.unified_diff(
            content.split("\n"), new_content.split("\n"),
            fromfile=f"a/{os.path.basename(path)}",
            tofile=f"b/{os.path.basename(path)}",
            lineterm="",
        ))
        diff_text = "\n".join(diff[:50])

        return {
            "success": True, "path": path,
            "replacements": count,
            "diff": diff_text,
        }
    except Exception as e:
        return {"error": str(e)}


registry.register(
    name="patch", toolset="file",
    schema={
        "description": "Precise find-and-replace in a file. Uses fuzzy matching (90%+ threshold) to handle minor whitespace differences.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path"},
                "old_string": {"type": "string", "description": "Exact text to find"},
                "new_string": {"type": "string", "description": "Replacement text"},
                "replace_all": {"type": "boolean", "description": "Replace all occurrences", "default": False},
            },
            "required": ["path", "old_string", "new_string"],
        },
    },
    handler=patch_handler, emoji="🩹",
)
