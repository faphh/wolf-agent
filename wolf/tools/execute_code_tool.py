"""Execute Code tool — Run Python scripts with tool access (Claude Code execute_code style).

The script can import from wolf.tools to call tools programmatically.
"""

import io
import sys
import json
import logging
import traceback
from typing import Any, Dict
from wolf.tools.registry import registry

logger = logging.getLogger(__name__)


def execute_code_handler(args: Dict[str, Any], context: Dict[str, Any] = None) -> Dict[str, Any]:
    """Execute a Python script with access to Wolf tools."""
    code = args.get("code", "")
    timeout = args.get("timeout", 300)

    if not code:
        return {"error": "No code provided"}

    # Capture stdout
    old_stdout = sys.stdout
    sys.stdout = captured = io.StringIO()

    local_ns = {"registry": registry, "json": json}

    try:
        exec(code, {"__builtins__": __builtins__, **local_ns}, local_ns)
        output = captured.getvalue()
        if len(output) > 50000:
            output = output[:25000] + "\n... [truncated] ...\n" + output[-25000:]
        return {"output": output, "exit_code": 0}
    except Exception as e:
        output = captured.getvalue()
        tb = traceback.format_exc()
        return {"output": output, "error": str(e), "traceback": tb[-2000:], "exit_code": 1}
    finally:
        sys.stdout = old_stdout


registry.register(
    name="execute_code", toolset="terminal",
    schema={
        "description": "Execute Python code with access to Wolf tools via `registry`. Use for batch operations, data processing, or complex multi-step logic. Print results to stdout.",
        "parameters": {
            "type": "object",
            "properties": {
                "code": {"type": "string", "description": "Python code to execute"},
            },
            "required": ["code"],
        },
    },
    handler=execute_code_handler, emoji="🐍",
)
