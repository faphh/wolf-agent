"""Refactor tool — Multi-file find-and-replace with safety checks.

Supports cross-file refactoring: rename symbols, move imports,
update references. Generates a diff preview before applying.
"""

import os
import re
import difflib
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from wolf.tools.registry import registry

logger = logging.getLogger(__name__)


def refactor_handler(args: Dict[str, Any], context=None) -> Dict[str, Any]:
    """Multi-file find and replace with preview."""
    find = args.get("find", "")
    replace = args.get("replace", "")
    file_glob = args.get("glob", "*.py")  # File pattern to search
    path = args.get("path", ".")
    preview = args.get("preview", True)  # Default: preview only, don't apply
    regex = args.get("regex", False)

    if not find:
        return {"error": "find pattern required"}

    # Find matching files
    root = Path(os.path.expanduser(path))
    if not root.exists():
        return {"error": f"Path not found: {path}"}

    patterns = [p.strip() for p in file_glob.split(",")]
    files = []
    for pat in patterns:
        files.extend(root.rglob(pat))
    files = [f for f in files if f.is_file() and ".git" not in str(f)]

    # Find and replace in each file
    changes = []
    total_replacements = 0

    for fpath in files:
        try:
            content = fpath.read_text(encoding="utf-8")
        except (UnicodeDecodeError, PermissionError):
            continue

        if regex:
            new_content, count = re.subn(find, replace, content)
        else:
            count = content.count(find)
            if count > 0:
                new_content = content.replace(find, replace)
            else:
                continue

        if count == 0:
            continue

        total_replacements += count

        # Generate diff
        diff = list(difflib.unified_diff(
            content.split("\n"), new_content.split("\n"),
            fromfile=f"a/{fpath.name}", tofile=f"b/{fpath.name}", lineterm="",
        ))

        changes.append({
            "file": str(fpath),
            "replacements": count,
            "diff": "\n".join(diff[:20]),  # First 20 lines of diff
        })

        # Apply if not preview
        if not preview:
            fpath.write_text(new_content, encoding="utf-8")

    return {
        "changes": changes,
        "total_files": len(changes),
        "total_replacements": total_replacements,
        "preview": preview,
        "message": f"{'Would replace' if preview else 'Replaced'} {total_replacements} occurrences in {len(changes)} files",
    }


registry.register(
    name="refactor", toolset="coding",
    schema={
        "description": "Multi-file find and replace. Preview mode (default) shows diff without applying. Supports regex.",
        "parameters": {
            "type": "object",
            "properties": {
                "find": {"type": "string", "description": "Text or regex to find"},
                "replace": {"type": "string", "description": "Replacement text"},
                "glob": {"type": "string", "description": "File pattern (default: *.py). Comma-separate for multiple.", "default": "*.py"},
                "path": {"type": "string", "description": "Root directory (default: cwd)"},
                "preview": {"type": "boolean", "description": "Preview only (default: true). Set false to apply.", "default": True},
                "regex": {"type": "boolean", "description": "Use regex matching (default: false)", "default": False},
            },
            "required": ["find", "replace"],
        },
    },
    handler=refactor_handler, emoji="🔄",
)

