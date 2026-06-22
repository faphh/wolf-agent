"""Interactive permission prompts for the terminal UI.

Provides y/n/a/d style prompts for tool permission decisions.
"""

import sys
from typing import Optional


def ask_permission(prompt_message: str, tool_name: str = "") -> str:
    """Ask user for permission via terminal prompt.

    Args:
        prompt_message: Description of what the tool wants to do
        tool_name: Name of the tool requesting permission

    Returns:
        "y" — approve once
        "a" — approve always (this tool, permanent)
        "n" — deny once
        "d" — deny always (this tool, permanent)
        ""  — user cancelled (Ctrl+C)
    """
    # Color the prompt
    icon = _get_tool_icon(tool_name)
    print(f"\n  \033[33m⚠ Permission required:\033[0m {icon} {tool_name}")
    print(f"  {prompt_message}")

    while True:
        try:
            choice = input(
                "  \033[36m[y]\033[0mes once / "
                "\033[32m[a]\033[0mlways / "
                "\033[31m[n]\033[0mo once / "
                "\033[91m[d]\033[0meny always: "
            ).strip().lower()

            if choice in ("y", "yes", ""):
                return "y"
            elif choice in ("a", "always"):
                return "a"
            elif choice in ("n", "no"):
                return "n"
            elif choice in ("d", "deny"):
                return "d"
            else:
                print("  \033[90mPlease enter y, a, n, or d\033[0m")
        except (KeyboardInterrupt, EOFError):
            print("\n  \033[31mDenied (interrupted)\033[0m")
            return "n"


def _get_tool_icon(tool_name: str) -> str:
    icons = {
        "terminal": "💻",
        "execute_code": "🐍",
        "write_file": "📝",
        "patch": "🩹",
        "git_commit": "✅",
        "git_stage": "📌",
    }
    return icons.get(tool_name, "🔧")


def permission_callback(tool_name: str, arguments: dict, prompt_message: str) -> Optional[bool]:
    """Callback for the conversation loop.

    Returns:
        True  — approved
        False — denied
        None  — use default behavior
    """
    decision = ask_permission(prompt_message, tool_name)

    from wolf.permissions import permission_manager

    if decision == "y":
        permission_manager.approve(tool_name)
        return True
    elif decision == "a":
        permission_manager.approve(tool_name, permanent=True)
        print(f"  \033[32m✓ {tool_name} will always be allowed\033[0m")
        return True
    elif decision == "n":
        return False
    elif decision == "d":
        permission_manager.deny(tool_name, permanent=True)
        print(f"  \033[31m✗ {tool_name} permanently denied\033[0m")
        return False

    return None
