"""Diagnostics tool — Run linters/analyzers and report errors.

Supports: python (ruff/mypy), javascript (eslint), generic (shellcheck).
Auto-detects project type and runs appropriate diagnostics.
"""

import os
import subprocess
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional
from wolf.tools.registry import registry

logger = logging.getLogger(__name__)


def _detect_project_type(cwd: str) -> str:
    """Detect project language from files present."""
    if os.path.exists(os.path.join(cwd, "pyproject.toml")) or os.path.exists(os.path.join(cwd, "setup.py")):
        return "python"
    if os.path.exists(os.path.join(cwd, "package.json")):
        return "javascript"
    if os.path.exists(os.path.join(cwd, "pom.xml")) or os.path.exists(os.path.join(cwd, "build.gradle")):
        return "java"
    # Check by file extensions
    for f in os.listdir(cwd):
        if f.endswith(".py"):
            return "python"
        if f.endswith((".ts", ".js", ".tsx", ".jsx")):
            return "javascript"
    return "unknown"


def diagnostics_handler(args: Dict[str, Any], context=None) -> Dict[str, Any]:
    """Run diagnostics on a file or project."""
    path = args.get("path", ".")
    tool = args.get("tool", "auto")  # auto, ruff, mypy, eslint, shellcheck
    fix = args.get("fix", False)

    cwd = path if os.path.isdir(path) else os.path.dirname(path) or "."
    target = path

    if tool == "auto":
        tool = _detect_project_type(cwd)
        if tool == "python":
            # Prefer ruff (fastest)
            tool = "ruff" if _cmd_exists("ruff") else "mypy" if _cmd_exists("mypy") else "pylint"
        elif tool == "javascript":
            tool = "eslint" if _cmd_exists("eslint") else "tsc"

    results = []

    if tool == "ruff":
        cmd = ["ruff", "check", target, "--output-format=json"]
        if fix:
            cmd.append("--fix")
        results = _run_diagnostics(cmd, "ruff")

    elif tool == "mypy":
        cmd = ["mypy", target, "--no-error-summary", "--show-column-numbers"]
        results = _run_diagnostics(cmd, "mypy")

    elif tool == "eslint":
        cmd = ["eslint", target, "--format=json"]
        results = _run_diagnostics(cmd, "eslint")

    elif tool == "shellcheck":
        cmd = ["shellcheck", "-f", "json", target]
        results = _run_diagnostics(cmd, "shellcheck")

    else:
        return {"error": f"Unsupported tool: {tool}. Supported: ruff, mypy, eslint, shellcheck"}

    error_count = sum(1 for r in results if r.get("severity") == "error")
    warning_count = sum(1 for r in results if r.get("severity") == "warning")

    return {
        "tool": tool,
        "diagnostics": results[:50],  # Limit output
        "total": len(results),
        "errors": error_count,
        "warnings": warning_count,
        "fix_applied": fix and tool in ("ruff",),
    }


def _run_diagnostics(cmd: List[str], tool: str) -> List[Dict[str, Any]]:
    """Run a diagnostic tool and parse output."""
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        output = result.stdout
        if not output and result.stderr:
            output = result.stderr

        if tool == "ruff":
            try:
                items = json.loads(output)
                return [
                    {"file": d.get("filename", ""), "line": d.get("location", {}).get("row", 0),
                     "col": d.get("location", {}).get("column", 0),
                     "severity": "error" if d.get("code", "").startswith("E") else "warning",
                     "message": d.get("message", ""), "code": d.get("code", "")}
                    for d in items
                ]
            except json.JSONDecodeError:
                pass

        # Generic line-based parsing
        diagnostics = []
        for line in output.split("\n"):
            if not line.strip():
                continue
            # Try to extract file:line:col: severity: message
            parts = line.split(":", 4)
            if len(parts) >= 4:
                diagnostics.append({
                    "file": parts[0].strip(),
                    "line": int(parts[1].strip()) if parts[1].strip().isdigit() else 0,
                    "col": int(parts[2].strip()) if parts[2].strip().isdigit() else 0,
                    "severity": "error" if "error" in line.lower() else "warning",
                    "message": parts[-1].strip() if len(parts) > 3 else line,
                })
        return diagnostics

    except subprocess.TimeoutExpired:
        return [{"severity": "error", "message": f"{tool} timed out"}]
    except FileNotFoundError:
        return [{"severity": "error", "message": f"{tool} not installed"}]
    except Exception as e:
        return [{"severity": "error", "message": str(e)}]


def _cmd_exists(cmd: str) -> bool:
    try:
        subprocess.run(["which", cmd], capture_output=True, timeout=2)
        return True
    except Exception:
        return False


registry.register(
    name="diagnostics", toolset="coding",
    schema={
        "description": "Run linters/analyzers on code. Auto-detects project type. Supports ruff, mypy, eslint, shellcheck.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File or directory path (default: cwd)"},
                "tool": {"type": "string", "description": "Diagnostic tool (auto/ruff/mypy/eslint/shellcheck)", "default": "auto"},
                "fix": {"type": "boolean", "description": "Auto-fix issues (ruff only)", "default": False},
            },
        },
    },
    handler=diagnostics_handler, emoji="🔬",
)

