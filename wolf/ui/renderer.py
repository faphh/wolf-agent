"""Rich-based renderer for Wolf output.

Provides markdown rendering, code highlighting, and structured tool display.
"""

import sys
from typing import Optional

# Lazy imports for graceful degradation
_rich_available = False
_console = None


def _init_rich():
    global _rich_available, _console
    if _console is not None:
        return
    try:
        from rich.console import Console
        from rich.theme import Theme
        _console = Console(theme=Theme({
            "wolf": "bold dark_orange",
            "tool": "cyan",
            "tool_result": "dim green",
            "error": "bold red",
            "thinking": "dim italic",
        }))
        _rich_available = True
    except ImportError:
        _rich_available = False


def render_response(text: str):
    """Render assistant response with markdown if possible."""
    _init_rich()

    if not _rich_available or not _console:
        print(f"\033[37m{text}\033[0m")
        return

    try:
        from rich.markdown import Markdown
        from rich.text import Text

        # Check if it looks like markdown
        md_markers = ["```", "# ", "- ", "**", "| ", "1.", "> ", "![", "[", "---"]
        is_md = any(m in text for m in md_markers)

        if is_md:
            md = Markdown(text)
            _console.print(md)
        else:
            _console.print(text)
    except Exception:
        print(f"\033[37m{text}\033[0m")


def render_tool_start(tool_name: str, tool_id: str = ""):
    """Render tool call start indicator."""
    _init_rich()
    icons = {
        "terminal": "💻", "read_file": "📖", "write_file": "📝", "patch": "🩹",
        "search_files": "🔍", "execute_code": "🐍", "web_search": "🔎",
        "web_fetch": "🌐", "memory": "🧠", "skill": "📚", "todo": "📋",
        "git_status": "📋", "git_diff": "📊", "git_log": "📜", "git_commit": "✅",
    }
    icon = icons.get(tool_name, "🔧")
    if _rich_available and _console:
        _console.print(f"  {icon} [{tool_name}]", style="tool", end=" ")
    else:
        sys.stdout.write(f"\n\033[36m  {icon} [{tool_name}]\033[0m ")
        sys.stdout.flush()


def render_tool_result(tool_name: str, success: bool, elapsed: float, summary: str = ""):
    """Render tool result indicator."""
    _init_rich()
    status = "✓" if success else "✗"
    style = "tool_result" if success else "error"
    msg = f"{status} ({elapsed:.1f}s)"
    if summary:
        msg += f" {summary[:50]}"

    if _rich_available and _console:
        _console.print(msg, style=style)
    else:
        color = "\033[32m" if success else "\033[31m"
        print(f"{color}{msg}\033[0m")


def render_thinking(text: str):
    """Render thinking/reasoning in dim style."""
    _init_rich()
    if _rich_available and _console:
        _console.print(text, style="thinking")
    else:
        print(f"\033[90m{text}\033[0m")


def render_error(text: str):
    """Render error message."""
    _init_rich()
    if _rich_available and _console:
        _console.print(f"✗ {text}", style="error")
    else:
        print(f"\033[31m✗ {text}\033[0m")


def render_stream_text(text: str):
    """Render streaming text chunk (no newline)."""
    sys.stdout.write(text)
    sys.stdout.flush()


def create_stream_callback():
    """Create a callback for streaming that renders nicely with spinner."""
    """Create a callback for streaming that renders nicely."""
    from wolf.providers.base import StreamChunk
    from wolf.ui.spinner import ThinkingSpinner

    current_tool = ""
    spinner = None

    def callback(chunk: StreamChunk):
        nonlocal current_tool, spinner

        # Stop spinner when any content arrives
        if spinner and chunk.type in ("text", "tool_use_start", "tool_result", "done", "error"):
            spinner.stop()
            spinner = None

        if chunk.type == "text":
            render_stream_text(chunk.content)
        elif chunk.type == "thinking":
            render_thinking(chunk.content)
        elif chunk.type == "thinking_start":
            # Start thinking spinner
            if not spinner:
                spinner = ThinkingSpinner("Thinking")
                spinner.start()
        elif chunk.type == "tool_use_start":
            current_tool = chunk.tool_name
            render_tool_start(chunk.tool_name, chunk.tool_call_id)
            # Start a tool execution spinner
            spinner = ThinkingSpinner(f"Running {chunk.tool_name}")
            spinner.start()
        elif chunk.type == "tool_use_delta":
            pass
        elif chunk.type == "tool_result":
            if spinner:
                spinner.stop()
                spinner = None
            success = "✓" in chunk.content
            elapsed = 0.0
            if "(" in chunk.content and "s)" in chunk.content:
                try:
                    elapsed = float(chunk.content.split("(")[1].rstrip("s)"))
                except (ValueError, IndexError):
                    pass
            render_tool_result(current_tool, success, elapsed)
        elif chunk.type == "done":
            if spinner:
                spinner.stop()
                spinner = None
            sys.stdout.write("\n")
            sys.stdout.flush()
        elif chunk.type == "error":
            render_error(chunk.error)
        elif chunk.type == "permission_request":
            pass

    return callback
