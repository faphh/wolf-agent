"""Terminal tool — Execute shell commands."""

import os
import subprocess
import threading
import time
import signal
import logging
from typing import Any, Dict, Optional
from wolf.tools.registry import registry

logger = logging.getLogger(__name__)

# Track background processes
_background_processes: Dict[str, subprocess.Popen] = {}


def terminal_handler(args: Dict[str, Any], context: Dict[str, Any] = None) -> Dict[str, Any]:
    """Execute a shell command."""
    command = args.get("command", "")
    timeout = args.get("timeout", 120)
    workdir = args.get("workdir", os.getcwd())
    background = args.get("background", False)

    if not command:
        return {"error": "No command provided"}

    if background:
        return _run_background(command, workdir)

    try:
        result = subprocess.run(
            command, shell=True, capture_output=True, text=True,
            timeout=timeout, cwd=workdir,
            env={**os.environ, "TERM": "dumb", "NO_COLOR": "1"},
        )
        output = result.stdout
        if result.stderr:
            output += f"\n[stderr]\n{result.stderr}" if output else result.stderr

        # Truncate very long output
        if len(output) > 50000:
            output = output[:25000] + f"\n... [truncated, {len(output)} chars total] ...\n" + output[-25000:]

        return {
            "output": output,
            "exit_code": result.returncode,
            "truncated": len(output) > 50000,
        }
    except subprocess.TimeoutExpired:
        return {"error": f"Command timed out after {timeout}s", "exit_code": -1}
    except Exception as e:
        return {"error": str(e), "exit_code": -1}


def _run_background(command: str, workdir: str) -> Dict[str, Any]:
    """Start a background process."""
    import uuid
    session_id = str(uuid.uuid4())[:8]
    try:
        proc = subprocess.Popen(
            command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            cwd=workdir, text=True,
            env={**os.environ, "TERM": "dumb", "NO_COLOR": "1"},
        )
        _background_processes[session_id] = proc
        return {"session_id": session_id, "pid": proc.pid, "status": "started"}
    except Exception as e:
        return {"error": str(e)}


TERMINAL_SCHEMA = {
    "description": "Execute shell commands. Returns stdout/stderr and exit code. Set background=true for long-running processes.",
    "parameters": {
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "The shell command to execute"},
            "timeout": {"type": "integer", "description": "Max seconds to wait (default 120)", "default": 120},
            "workdir": {"type": "string", "description": "Working directory (default: cwd)"},
            "background": {"type": "boolean", "description": "Run in background", "default": False},
        },
        "required": ["command"],
    },
}

registry.register(
    name="terminal", toolset="terminal", schema=TERMINAL_SCHEMA,
    handler=terminal_handler, emoji="💻",
    description="Execute shell commands",
)
