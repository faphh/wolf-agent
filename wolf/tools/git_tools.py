"""Git tools — Integrated git operations for Wolf.

Provides git status, diff, log, commit, blame, and file change tracking
as first-class tools instead of relying on raw terminal commands.
"""

import os
import subprocess
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional
from wolf.tools.registry import registry

logger = logging.getLogger(__name__)


def _run_git(args: List[str], cwd: str = ".") -> Dict[str, Any]:
    """Run a git command and return structured result."""
    try:
        result = subprocess.run(
            ["git"] + args,
            capture_output=True, text=True, timeout=30,
            cwd=cwd, env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
        )
        return {
            "output": result.stdout.strip(),
            "error": result.stderr.strip() if result.returncode != 0 else "",
            "exit_code": result.returncode,
        }
    except subprocess.TimeoutExpired:
        return {"output": "", "error": "Git command timed out", "exit_code": -1}
    except FileNotFoundError:
        return {"output": "", "error": "Git not installed", "exit_code": -1}


def _find_repo_root(cwd: str = ".") -> Optional[str]:
    """Find the git repo root directory."""
    r = _run_git(["rev-parse", "--show-toplevel"], cwd)
    if r["exit_code"] == 0:
        return r["output"]
    return None


# ── git status ────────────────────────────────────────────────────

def git_status_handler(args: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Show working tree status with structured output."""
    cwd = args.get("cwd", ".")
    short = args.get("short", True)

    cmd = ["status", "--porcelain=v2", "--branch"]
    if short:
        cmd = ["status", "--short", "--branch"]

    r = _run_git(cmd, cwd)
    if r["exit_code"] != 0:
        return {"error": r["error"]}

    # Parse porcelain v2 format
    output = r["output"]
    lines = output.split("\n") if output else []

    branch_info = {}
    changes = []
    for line in lines:
        if line.startswith("#"):
            # Branch info
            if line.startswith("# branch.head"):
                branch_info["head"] = line.split()[-1]
            elif line.startswith("# branch.upstream"):
                branch_info["upstream"] = line.split()[-1]
        elif line.strip():
            # File change: XY <path>
            if len(line) >= 3:
                status = line[:2].strip()
                path = line[3:]
                changes.append({"status": status, "path": path})

    return {
        "branch": branch_info.get("head", "unknown"),
        "upstream": branch_info.get("upstream", ""),
        "changes": changes,
        "summary": f"{len(changes)} changed files",
        "raw": output,
    }


# ── git diff ──────────────────────────────────────────────────────

def git_diff_handler(args: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Show file differences. Supports staged, unstaged, and specific files."""
    cwd = args.get("cwd", ".")
    staged = args.get("staged", False)
    file_path = args.get("file", "")
    stat = args.get("stat", False)
    max_lines = args.get("max_lines", 500)

    cmd = ["diff"]
    if staged:
        cmd.append("--staged")
    if stat:
        cmd.append("--stat")
    if file_path:
        cmd.extend(["--", file_path])

    r = _run_git(cmd, cwd)
    if r["exit_code"] != 0:
        return {"error": r["error"]}

    output = r["output"]
    if len(output.split("\n")) > max_lines:
        lines = output.split("\n")
        output = "\n".join(lines[:max_lines]) + f"\n... [{len(lines) - max_lines} more lines]"

    return {"diff": output, "staged": staged, "file": file_path}


# ── git log ───────────────────────────────────────────────────────

def git_log_handler(args: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Show commit history."""
    cwd = args.get("cwd", ".")
    count = args.get("count", 10)
    file_path = args.get("file", "")
    oneline = args.get("oneline", True)

    cmd = ["log", f"-{count}", "--format=%H|%h|%an|%ai|%s"]
    if oneline:
        cmd = ["log", f"-{count}", "--oneline"]
    if file_path:
        cmd.extend(["--", file_path])

    r = _run_git(cmd, cwd)
    if r["exit_code"] != 0:
        return {"error": r["error"]}

    return {"log": r["output"], "count": count}


# ── git show ──────────────────────────────────────────────────────

def git_show_handler(args: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Show a commit, tag, or file content at a revision."""
    cwd = args.get("cwd", ".")
    ref = args.get("ref", "HEAD")
    file_path = args.get("file", "")
    stat = args.get("stat", False)

    cmd = ["show", ref]
    if stat:
        cmd.append("--stat")
    if file_path:
        cmd.extend(["--", file_path])

    r = _run_git(cmd, cwd)
    if r["exit_code"] != 0:
        return {"error": r["error"]}

    output = r["output"]
    if len(output) > 10000:
        output = output[:8000] + f"\n... [truncated, {len(output)} chars total]"

    return {"content": output, "ref": ref}


# ── git blame ─────────────────────────────────────────────────────

def git_blame_handler(args: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Show line-by-line file annotations."""
    cwd = args.get("cwd", ".")
    file_path = args.get("file", "")
    line_range = args.get("lines", "")  # e.g., "10,20"

    if not file_path:
        return {"error": "file path required"}

    cmd = ["blame", "--porcelain"]
    if line_range:
        cmd.extend(["-L", line_range])
    cmd.append(file_path)

    r = _run_git(cmd, cwd)
    if r["exit_code"] != 0:
        return {"error": r["error"]}

    # Parse porcelain format into readable annotations
    annotations = []
    current = {}
    for line in r["output"].split("\n"):
        if line.startswith("\t"):
            annotations.append({
                "commit": current.get("summary", "")[:8],
                "author": current.get("author", ""),
                "line": line[1:],
            })
        elif " " in line:
            key, _, val = line.partition(" ")
            if key == "summary":
                current["summary"] = val
            elif key == "author":
                current["author"] = val

    return {"file": file_path, "annotations": annotations[:200]}


# ── git commit ────────────────────────────────────────────────────

def git_commit_handler(args: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Create a git commit with a message."""
    cwd = args.get("cwd", ".")
    message = args.get("message", "")
    add_all = args.get("add_all", False)
    amend = args.get("amend", False)

    if not message:
        return {"error": "commit message required"}

    if add_all:
        _run_git(["add", "-A"], cwd)

    cmd = ["commit", "-m", message]
    if amend:
        cmd.append("--amend")

    r = _run_git(cmd, cwd)
    if r["exit_code"] != 0:
        return {"error": r["error"] or r["output"]}

    return {"success": True, "output": r["output"]}


# ── git branch ────────────────────────────────────────────────────

def git_branch_handler(args: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """List, create, or switch branches."""
    cwd = args.get("cwd", ".")
    action = args.get("action", "list")  # list, create, switch, delete
    name = args.get("name", "")

    if action == "list":
        r = _run_git(["branch", "-a", "--format=%(refname:short)%(HEAD)"], cwd)
        if r["exit_code"] != 0:
            return {"error": r["error"]}
        branches = []
        for line in r["output"].split("\n"):
            if line.strip():
                current = line.endswith("*")
                name_str = line.rstrip("*").strip()
                branches.append({"name": name_str, "current": current})
        return {"branches": branches}

    elif action == "create":
        if not name:
            return {"error": "branch name required"}
        r = _run_git(["checkout", "-b", name], cwd)
        return {"success": r["exit_code"] == 0, "output": r["output"], "error": r["error"]}

    elif action == "switch":
        if not name:
            return {"error": "branch name required"}
        r = _run_git(["checkout", name], cwd)
        return {"success": r["exit_code"] == 0, "output": r["output"], "error": r["error"]}

    elif action == "delete":
        if not name:
            return {"error": "branch name required"}
        r = _run_git(["branch", "-d", name], cwd)
        return {"success": r["exit_code"] == 0, "output": r["output"], "error": r["error"]}

    return {"error": f"Unknown action: {action}"}


# ── git stage ─────────────────────────────────────────────────────

def git_stage_handler(args: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Stage files for commit."""
    cwd = args.get("cwd", ".")
    files = args.get("files", [])
    unstage = args.get("unstage", False)

    if not files:
        return {"error": "files required"}

    if unstage:
        cmd = ["reset", "HEAD", "--"] + files
    else:
        cmd = ["add"] + files

    r = _run_git(cmd, cwd)
    return {"success": r["exit_code"] == 0, "output": r["output"], "error": r["error"]}


# ── git file history ──────────────────────────────────────────────

def git_file_history_handler(args: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Show the change history of a specific file."""
    cwd = args.get("cwd", ".")
    file_path = args.get("file", "")
    count = args.get("count", 10)

    if not file_path:
        return {"error": "file path required"}

    cmd = ["log", f"-{count}", "--oneline", "--follow", "--", file_path]
    r = _run_git(cmd, cwd)
    if r["exit_code"] != 0:
        return {"error": r["error"]}

    return {"file": file_path, "history": r["output"]}


# ── Register all git tools ────────────────────────────────────────

registry.register(
    name="git_status", toolset="git",
    schema={
        "description": "Show git working tree status — changed files, branch, ahead/behind.",
        "parameters": {
            "type": "object",
            "properties": {
                "cwd": {"type": "string", "description": "Working directory (default: cwd)"},
                "short": {"type": "boolean", "description": "Short format (default: true)", "default": True},
            },
        },
    },
    handler=git_status_handler, emoji="📋",
)

registry.register(
    name="git_diff", toolset="git",
    schema={
        "description": "Show file differences. Compare staged, unstaged, or specific files.",
        "parameters": {
            "type": "object",
            "properties": {
                "cwd": {"type": "string", "description": "Working directory"},
                "staged": {"type": "boolean", "description": "Show staged changes (default: false)", "default": False},
                "file": {"type": "string", "description": "Specific file to diff"},
                "stat": {"type": "boolean", "description": "Show stat only (default: false)", "default": False},
                "max_lines": {"type": "integer", "description": "Max output lines (default: 500)"},
            },
        },
    },
    handler=git_diff_handler, emoji="📊",
)

registry.register(
    name="git_log", toolset="git",
    schema={
        "description": "Show commit history.",
        "parameters": {
            "type": "object",
            "properties": {
                "cwd": {"type": "string", "description": "Working directory"},
                "count": {"type": "integer", "description": "Number of commits (default: 10)"},
                "file": {"type": "string", "description": "Filter by file"},
                "oneline": {"type": "boolean", "description": "One-line format", "default": True},
            },
        },
    },
    handler=git_log_handler, emoji="📜",
)

registry.register(
    name="git_show", toolset="git",
    schema={
        "description": "Show a commit, tag, or file content at a specific revision.",
        "parameters": {
            "type": "object",
            "properties": {
                "cwd": {"type": "string", "description": "Working directory"},
                "ref": {"type": "string", "description": "Git ref (commit, tag, branch, HEAD~1)", "default": "HEAD"},
                "file": {"type": "string", "description": "Specific file"},
                "stat": {"type": "boolean", "description": "Show stat only", "default": False},
            },
        },
    },
    handler=git_show_handler, emoji="🔎",
)

registry.register(
    name="git_blame", toolset="git",
    schema={
        "description": "Show line-by-line annotations for a file (who changed what).",
        "parameters": {
            "type": "object",
            "properties": {
                "cwd": {"type": "string", "description": "Working directory"},
                "file": {"type": "string", "description": "File to annotate"},
                "lines": {"type": "string", "description": "Line range (e.g., '10,20')"},
            },
            "required": ["file"],
        },
    },
    handler=git_blame_handler, emoji="👤",
)

registry.register(
    name="git_commit", toolset="git",
    schema={
        "description": "Create a git commit.",
        "parameters": {
            "type": "object",
            "properties": {
                "cwd": {"type": "string", "description": "Working directory"},
                "message": {"type": "string", "description": "Commit message"},
                "add_all": {"type": "boolean", "description": "Stage all changes first", "default": False},
                "amend": {"type": "boolean", "description": "Amend last commit", "default": False},
            },
            "required": ["message"],
        },
    },
    handler=git_commit_handler, emoji="✅",
)

registry.register(
    name="git_branch", toolset="git",
    schema={
        "description": "List, create, switch, or delete branches.",
        "parameters": {
            "type": "object",
            "properties": {
                "cwd": {"type": "string", "description": "Working directory"},
                "action": {"type": "string", "enum": ["list", "create", "switch", "delete"], "default": "list"},
                "name": {"type": "string", "description": "Branch name (for create/switch/delete)"},
            },
        },
    },
    handler=git_branch_handler, emoji="🌿",
)

registry.register(
    name="git_stage", toolset="git",
    schema={
        "description": "Stage or unstage files for commit.",
        "parameters": {
            "type": "object",
            "properties": {
                "cwd": {"type": "string", "description": "Working directory"},
                "files": {"type": "array", "items": {"type": "string"}, "description": "Files to stage/unstage"},
                "unstage": {"type": "boolean", "description": "Unstage instead of stage", "default": False},
            },
            "required": ["files"],
        },
    },
    handler=git_stage_handler, emoji="📌",
)

registry.register(
    name="git_file_history", toolset="git",
    schema={
        "description": "Show the change history of a specific file.",
        "parameters": {
            "type": "object",
            "properties": {
                "cwd": {"type": "string", "description": "Working directory"},
                "file": {"type": "string", "description": "File to check history"},
                "count": {"type": "integer", "description": "Number of entries (default: 10)"},
            },
            "required": ["file"],
        },
    },
    handler=git_file_history_handler, emoji="🕐",
)
