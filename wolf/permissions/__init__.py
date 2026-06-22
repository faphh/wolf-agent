"""Wolf Permission System.

Three-tier permission model:
1. Tool-level: each tool has a default permission level
2. Rule-based: user can override per tool/path/command
3. Interactive: ask user for uncertain operations

Permission levels:
  auto_allow  — execute without asking
  ask_once    — ask user, remember for this session
  ask_always  — ask user every time
  deny        — block execution

Persisted in ~/.wolf/permissions.yaml
"""

import os
import re
import yaml
import logging
from pathlib import Path
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)

PERMISSIONS_FILE = Path.home() / ".wolf" / "permissions.yaml"


# ── Default Permission Levels ─────────────────────────────────────

TOOL_DEFAULT_PERMISSIONS: Dict[str, str] = {
    # Read-only — always safe
    "read_file": "auto_allow",
    "search_files": "auto_allow",
    "web_search": "auto_allow",
    "web_fetch": "auto_allow",
    "memory": "auto_allow",
    "skill": "auto_allow",
    "todo": "auto_allow",
    "git_status": "auto_allow",
    "git_diff": "auto_allow",
    "git_log": "auto_allow",
    "git_show": "auto_allow",
    "git_blame": "auto_allow",
    "git_branch": "auto_allow",
    "git_file_history": "auto_allow",

    # Write — ask once per session
    "write_file": "ask_once",
    "patch": "ask_once",
    "git_commit": "ask_once",
    "git_stage": "ask_once",

    # Execution — ask each time for safety
    "terminal": "ask_always",
    "execute_code": "ask_always",

    # MCP tools — ask once
    # mcp_* tools default to ask_once
}


# ── Shell Command Safety ──────────────────────────────────────────

# Commands that are always safe (read-only, info gathering)
SAFE_COMMANDS: Set[str] = {
    "ls", "cat", "head", "tail", "wc", "echo", "pwd", "whoami",
    "date", "which", "whereis", "file", "stat", "du", "df",
    "git", "grep", "rg", "find", "sort", "uniq", "diff",
    "python", "python3", "node", "npm", "pip", "conda",
    "curl", "wget", "dig", "ping", "traceroute",
    "ps", "top", "htop", "free", "uname", "env", "printenv",
    "jq", "sed", "awk", "tr", "cut", "tee",
}

# Commands that modify the system — always ask
DESTRUCTIVE_COMMANDS: Set[str] = {
    "rm", "rmdir", "mv", "chmod", "chown", "chgrp",
    "mkfs", "fdisk", "mount", "umount",
    "kill", "killall", "pkill",
    "shutdown", "reboot", "halt",
    "useradd", "userdel", "groupadd", "passwd",
    "iptables", "ufw", "firewall-cmd",
    "drop", "truncate", "delete",  # SQL
}

# Commands that are commonly safe but write to filesystem
WRITE_COMMANDS: Set[str] = {
    "cp", "mkdir", "touch", "ln", "tar", "zip", "unzip",
    "git",  # git is safe for read ops, but commit/push need checking
    "pip install", "npm install", "conda install",
    "brew", "apt", "yum",
}

# Dangerous patterns in shell commands
DANGEROUS_PATTERNS: List[Tuple[str, str]] = [
    (r">\s*/dev/sd", "writes to block device"),
    (r"dd\s+if=", "raw disk write"),
    (r"curl.*\|\s*(ba)?sh", "pipes remote content to shell"),
    (r"wget.*\|\s*(ba)?sh", "pipes remote content to shell"),
    (r"eval\s*\(", "evaluates arbitrary code"),
    (r"sudo\s+", "elevated privileges"),
    (r">\s*/etc/", "writes to system config"),
    (r"rm\s+-rf\s+/", "recursive delete from root"),
    (r"chmod\s+777", "world-writable permissions"),
    (r"--no-preserve-root", "bypasses root protection"),
]


# ── Permission Decision ───────────────────────────────────────────

@dataclass
class PermissionDecision:
    """Result of a permission check."""
    allowed: bool
    level: str  # "auto_allow", "ask_once", "ask_always", "deny"
    reason: str = ""
    needs_user_input: bool = False
    prompt_message: str = ""


# ── Permission Manager ────────────────────────────────────────────

class PermissionManager:
    """Manages tool execution permissions."""

    def __init__(self):
        self._session_approvals: Set[str] = set()  # tool names approved this session
        self._rules: Dict[str, str] = {}  # tool_name -> permission level
        self._path_allowlists: Dict[str, List[str]] = {}  # tool -> allowed paths
        self._load_rules()

    def _load_rules(self):
        """Load permission rules from file."""
        if not PERMISSIONS_FILE.exists():
            return
        try:
            with open(PERMISSIONS_FILE, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            self._rules = data.get("rules", {})
            self._path_allowlists = data.get("path_allowlists", {})
        except Exception as e:
            logger.warning(f"Failed to load permissions: {e}")

    def save_rules(self):
        """Persist permission rules to file."""
        PERMISSIONS_FILE.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "rules": self._rules,
            "path_allowlists": self._path_allowlists,
        }
        with open(PERMISSIONS_FILE, "w", encoding="utf-8") as f:
            yaml.dump(data, f, default_flow_style=False, allow_unicode=True)
        os.chmod(PERMISSIONS_FILE, 0o600)

    def check_permission(self, tool_name: str, arguments: Dict[str, Any]) -> PermissionDecision:
        """Check if a tool call is permitted.

        Args:
            tool_name: Name of the tool
            arguments: Tool arguments (for context-aware checks)

        Returns:
            PermissionDecision with allowed flag and details
        """
        # 1. Check explicit rules first
        rule_level = self._rules.get(tool_name)

        # 2. Fall back to defaults
        if rule_level is None:
            if tool_name.startswith("mcp_"):
                rule_level = "ask_once"
            else:
                rule_level = TOOL_DEFAULT_PERMISSIONS.get(tool_name, "ask_once")

        # 3. Deny is absolute
        if rule_level == "deny":
            return PermissionDecision(
                allowed=False, level="deny",
                reason=f"Tool '{tool_name}' is denied by permission rules",
            )

        # 4. Auto-allow
        if rule_level == "auto_allow":
            return PermissionDecision(allowed=True, level="auto_allow")

        # 5. Ask-once: check session cache
        if rule_level == "ask_once":
            if tool_name in self._session_approvals:
                return PermissionDecision(allowed=True, level="ask_once",
                                          reason="Previously approved this session")
            # Need to ask
            prompt = self._build_prompt(tool_name, arguments)
            return PermissionDecision(
                allowed=False, level="ask_once",
                needs_user_input=True, prompt_message=prompt,
            )

        # 6. Ask-always: always need user input
        if rule_level == "ask_always":
            # But apply shell safety heuristics for terminal commands
            if tool_name in ("terminal", "execute_code"):
                safety = self._check_shell_safety(arguments)
                if safety.allowed:
                    return safety

            prompt = self._build_prompt(tool_name, arguments)
            return PermissionDecision(
                allowed=False, level="ask_always",
                needs_user_input=True, prompt_message=prompt,
            )

        # Default: ask
        return PermissionDecision(
            allowed=False, level="ask_once",
            needs_user_input=True,
            prompt_message=f"Allow {tool_name}?",
        )

    def approve(self, tool_name: str, permanent: bool = False):
        """Record user approval for a tool."""
        self._session_approvals.add(tool_name)
        if permanent:
            self._rules[tool_name] = "auto_allow"
            self.save_rules()

    def deny(self, tool_name: str, permanent: bool = False):
        """Record user denial for a tool."""
        if permanent:
            self._rules[tool_name] = "deny"
            self.save_rules()

    def set_rule(self, tool_name: str, level: str):
        """Set a permission rule."""
        self._rules[tool_name] = level
        self.save_rules()

    def get_rules(self) -> Dict[str, str]:
        """Get all current rules."""
        result = {}
        for tool_name in TOOL_DEFAULT_PERMISSIONS:
            result[tool_name] = self._rules.get(tool_name, TOOL_DEFAULT_PERMISSIONS[tool_name])
        for tool_name, level in self._rules.items():
            if tool_name not in result:
                result[tool_name] = level
        return result

    def _check_shell_safety(self, arguments: Dict[str, Any]) -> PermissionDecision:
        """Heuristic check for shell command safety."""
        command = arguments.get("command", "")
        if not command:
            return PermissionDecision(allowed=False, level="ask_always",
                                      needs_user_input=True,
                                      prompt_message="Empty command — allow?")

        # Extract the first command word
        cmd_parts = command.strip().split()
        if not cmd_parts:
            return PermissionDecision(allowed=False, level="ask_always",
                                      needs_user_input=True)

        base_cmd = os.path.basename(cmd_parts[0])

        # Check dangerous patterns first
        for pattern, reason in DANGEROUS_PATTERNS:
            if re.search(pattern, command, re.IGNORECASE):
                return PermissionDecision(
                    allowed=False, level="ask_always",
                    needs_user_input=True,
                    prompt_message=f"⚠️  Dangerous pattern detected: {reason}\n  Command: {command}\n  Allow?",
                )

        # Check destructive commands
        if base_cmd in DESTRUCTIVE_COMMANDS:
            return PermissionDecision(
                allowed=False, level="ask_always",
                needs_user_input=True,
                prompt_message=f"⚠️  Destructive command: {command}\n  Allow?",
            )

        # Check if it's a safe read-only command
        if base_cmd in SAFE_COMMANDS:
            # But check for output redirection to important paths
            if re.search(r">\s*(/etc/|/usr/|/bin/|/sbin/)", command):
                return PermissionDecision(
                    allowed=False, level="ask_always",
                    needs_user_input=True,
                    prompt_message=f"⚠️  Redirects to system path: {command}\n  Allow?",
                )
            return PermissionDecision(allowed=True, level="auto_allow",
                                      reason=f"Safe command: {base_cmd}")

        # Check git sub-commands
        if base_cmd == "git" and len(cmd_parts) > 1:
            subcmd = cmd_parts[1]
            safe_git = {"status", "log", "diff", "show", "branch", "remote",
                        "describe", "rev-parse", "ls-files", "ls-remote"}
            if subcmd in safe_git:
                return PermissionDecision(allowed=True, level="auto_allow",
                                          reason=f"Safe git command: git {subcmd}")

        # Write commands — ask once
        if base_cmd in WRITE_COMMANDS:
            return PermissionDecision(
                allowed=False, level="ask_once",
                needs_user_input=True,
                prompt_message=f"Allow write command: {command}?",
            )

        # Unknown command — ask
        return PermissionDecision(
            allowed=False, level="ask_always",
            needs_user_input=True,
            prompt_message=f"Allow: {command}?",
        )

    def _build_prompt(self, tool_name: str, arguments: Dict[str, Any]) -> str:
        """Build a user-friendly permission prompt."""
        if tool_name == "terminal":
            cmd = arguments.get("command", "")
            return f"Execute shell command: {cmd}"
        elif tool_name == "execute_code":
            code = arguments.get("code", "")
            preview = code[:100] + "..." if len(code) > 100 else code
            return f"Execute Python code:\n  {preview}"
        elif tool_name == "write_file":
            path = arguments.get("path", "")
            return f"Write to file: {path}"
        elif tool_name == "patch":
            path = arguments.get("path", "")
            return f"Patch file: {path}"
        else:
            return f"Use tool: {tool_name}"

    def format_rules_display(self) -> str:
        """Format rules for display."""
        lines = ["\n  Permission Rules:"]
        rules = self.get_rules()
        for tool, level in sorted(rules.items()):
            icon = {"auto_allow": "✅", "ask_once": "🔶", "ask_always": "❓", "deny": "🚫"}.get(level, "❓")
            lines.append(f"    {icon} {tool:20s} → {level}")
        return "\n".join(lines)


# Singleton
permission_manager = PermissionManager()
