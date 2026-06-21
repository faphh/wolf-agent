"""File tools — read, write, search files."""

import os
import re
import logging
from pathlib import Path
from typing import Any, Dict
from wolf.tools.registry import registry

logger = logging.getLogger(__name__)


def file_read_handler(args: Dict[str, Any], context: Dict[str, Any] = None) -> Dict[str, Any]:
    """Read a file with line numbers and pagination."""
    path = args.get("path", "")
    offset = max(1, args.get("offset", 1))
    limit = min(2000, max(1, args.get("limit", 500)))

    if not path:
        return {"error": "No path provided"}

    path = os.path.expanduser(path)
    if not os.path.exists(path):
        return {"error": f"File not found: {path}"}

    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()

        total = len(lines)
        start = offset - 1
        end = min(start + limit, total)
        selected = lines[start:end]

        content = "".join(f"{i+1}|{line}" for i, line in enumerate(selected, start=start))
        return {"content": content, "total_lines": total, "truncated": end < total}
    except Exception as e:
        return {"error": str(e)}


def file_write_handler(args: Dict[str, Any], context: Dict[str, Any] = None) -> Dict[str, Any]:
    """Write content to a file (overwrites entirely)."""
    path = args.get("path", "")
    content = args.get("content", "")

    if not path:
        return {"error": "No path provided"}

    path = os.path.expanduser(path)
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return {"success": True, "path": path, "bytes_written": len(content.encode())}
    except Exception as e:
        return {"error": str(e)}


def search_files_handler(args: Dict[str, Any], context: Dict[str, Any] = None) -> Dict[str, Any]:
    """Search file contents or find files by name. Uses ripgrep if available, falls back to grep."""
    import subprocess
    pattern = args.get("pattern", "")
    path = args.get("path", ".")
    target = args.get("target", "content")  # "content" or "files"
    file_glob = args.get("file_glob", "")
    limit = args.get("limit", 50)

    if not pattern:
        return {"error": "No pattern provided"}

    path = os.path.expanduser(path)

    try:
        if target == "files":
            # Find files by name pattern
            cmd = ["find", path, "-name", pattern, "-maxdepth", "5"]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            files = result.stdout.strip().split("\n")[:limit]
            return {"files": [f for f in files if f]}
        else:
            # Search file contents - try ripgrep first
            cmd = ["rg", "--no-heading", "-n", "-l" if args.get("files_only", False) else "",
                   "--max-count", str(limit)]
            if file_glob:
                cmd += ["-g", file_glob]
            cmd += [pattern, path]
            cmd = [c for c in cmd if c]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            output = result.stdout[:50000] if result.stdout else ""
            matches = output.strip().split("\n") if output else []
            return {"matches": [m for m in matches if m][:limit], "total": len(matches)}
    except FileNotFoundError:
        # Fallback to grep
        cmd = ["grep", "-r", "-n", pattern, path]
        if file_glob:
            cmd = ["find", path, "-name", file_glob, "-exec", "grep", "-n", pattern, "{}", "+"]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        output = result.stdout[:50000] if result.stdout else ""
        matches = output.strip().split("\n") if output else []
        return {"matches": [m for m in matches if m][:limit]}
    except Exception as e:
        return {"error": str(e)}


# Register tools
registry.register(
    name="read_file", toolset="file",
    schema={
        "description": "Read a text file with line numbers. Use offset/limit for pagination.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path (absolute or relative)"},
                "offset": {"type": "integer", "description": "Start line (1-indexed, default 1)"},
                "limit": {"type": "integer", "description": "Max lines to read (default 500)"},
            },
            "required": ["path"],
        },
    },
    handler=file_read_handler, emoji="📖",
)

registry.register(
    name="write_file", toolset="file",
    schema={
        "description": "Write content to a file. Creates parent dirs. OVERWRITES entire file.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path"},
                "content": {"type": "string", "description": "Content to write"},
            },
            "required": ["path", "content"],
        },
    },
    handler=file_write_handler, emoji="📝",
)

registry.register(
    name="search_files", toolset="file",
    schema={
        "description": "Search file contents (regex) or find files by name. Uses ripgrep when available.",
        "parameters": {
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "Regex pattern or filename glob"},
                "path": {"type": "string", "description": "Directory to search (default: cwd)"},
                "target": {"type": "string", "enum": ["content", "files"], "description": "Search mode"},
                "file_glob": {"type": "string", "description": "Filter by file pattern (e.g. *.py)"},
                "limit": {"type": "integer", "description": "Max results (default 50)"},
            },
            "required": ["pattern"],
        },
    },
    handler=search_files_handler, emoji="🔍",
)
