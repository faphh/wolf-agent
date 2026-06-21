"""Wolf Tool Registry — Central tool registration and dispatch.

Design: Hermes-style self-registration with AST-based discovery.
Each tool module calls `registry.register()` at module level.
The registry is a thread-safe singleton.

Import chain (circular-import safe):
    tools/registry.py  (no imports from tool files)
           ^
    tools/*.py  (import from tools.registry at module level)
           ^
    agent.py  (imports registry + triggers discovery)
"""

import ast
import importlib
import json
import logging
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


class ToolEntry:
    """A registered tool."""
    __slots__ = ("name", "toolset", "schema", "handler", "check_fn",
                 "description", "emoji", "_check_result", "_check_ts")

    def __init__(self, name: str, toolset: str, schema: Dict[str, Any],
                 handler: Callable, check_fn: Optional[Callable] = None,
                 description: str = "", emoji: str = ""):
        self.name = name
        self.toolset = toolset
        self.schema = schema
        self.handler = handler
        self.check_fn = check_fn
        self.description = description
        self.emoji = emoji
        self._check_result: Optional[bool] = None
        self._check_ts: float = 0


class ToolRegistry:
    """Thread-safe singleton tool registry."""
    _instance: Optional["ToolRegistry"] = None
    _lock = threading.Lock()
    _tools: Dict[str, "ToolEntry"]
    _toolsets: Dict[str, List[str]]
    _rt_lock: threading.RLock
    _generation: int

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    inst = super().__new__(cls)
                    inst._tools = {}
                    inst._toolsets = {}
                    inst._rt_lock = threading.RLock()
                    inst._generation = 0
                    cls._instance = inst
        return cls._instance

    def register(self, name: str, toolset: str, schema: Dict[str, Any],
                 handler: Callable, check_fn: Optional[Callable] = None,
                 description: str = "", emoji: str = "",
                 override: bool = False) -> None:
        """Register a tool. Called at module level by tool files."""
        with self._rt_lock:
            if name in self._tools and not override:
                existing = self._tools[name]
                if existing.toolset != toolset:
                    logger.warning(
                        f"Tool '{name}' already registered in toolset "
                        f"'{existing.toolset}', skipping re-register in '{toolset}'"
                    )
                    return
            self._tools[name] = ToolEntry(
                name=name, toolset=toolset, schema=schema,
                handler=handler, check_fn=check_fn,
                description=description, emoji=emoji,
            )
            if toolset not in self._toolsets:
                self._toolsets[toolset] = []
            if name not in self._toolsets[toolset]:
                self._toolsets[toolset].append(name)
            self._generation += 1

    def deregister(self, name: str) -> None:
        with self._rt_lock:
            if name in self._tools:
                entry = self._tools.pop(name)
                if entry.toolset in self._toolsets:
                    self._toolsets[entry.toolset] = [
                        n for n in self._toolsets[entry.toolset] if n != name
                    ]
                self._generation += 1

    def get(self, name: str) -> Optional[ToolEntry]:
        return self._tools.get(name)

    def get_all(self) -> Dict[str, ToolEntry]:
        with self._rt_lock:
            return dict(self._tools)

    def get_toolset(self, name: str) -> List[str]:
        with self._rt_lock:
            return list(self._toolsets.get(name, []))

    def get_available_tools(self, toolsets: Optional[List[str]] = None) -> List[ToolEntry]:
        """Get tools filtered by toolsets, with check_fn evaluation."""
        with self._rt_lock:
            if toolsets is None:
                candidates = list(self._tools.values())
            else:
                names: Set[str] = set()
                for ts in toolsets:
                    names.update(self._toolsets.get(ts, []))
                candidates = [self._tools[n] for n in names if n in self._tools]

            result = []
            for entry in candidates:
                if self._check_available(entry):
                    result.append(entry)
            return result

    def get_tool_definitions(self, toolsets: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """Get tool schema definitions for the LLM API."""
        tools = self.get_available_tools(toolsets)
        return [
            {"type": "function", "function": {"name": t.name, **t.schema}}
            for t in tools
        ]

    def get_anthropic_tool_definitions(self, toolsets: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """Get tool definitions in Anthropic format."""
        tools = self.get_available_tools(toolsets)
        defs = []
        for t in tools:
            schema = t.schema
            defs.append({
                "name": t.name,
                "description": schema.get("description", t.description),
                "input_schema": schema.get("parameters", {"type": "object", "properties": {}}),
            })
        return defs

    def dispatch(self, name: str, arguments: Dict[str, Any],
                 context: Optional[Dict[str, Any]] = None) -> Any:
        """Dispatch a tool call to its handler."""
        entry = self._tools.get(name)
        if entry is None:
            return {"error": f"Unknown tool: {name}"}
        try:
            return entry.handler(arguments, context=context or {})
        except Exception as e:
            logger.exception(f"Tool '{name}' execution failed")
            return {"error": f"Tool execution failed: {str(e)}"}

    def _check_available(self, entry: ToolEntry) -> bool:
        """Evaluate check_fn with 30s TTL cache."""
        if entry.check_fn is None:
            return True
        now = time.time()
        if entry._check_result is not None and (now - entry._check_ts) < 30:
            return entry._check_result
        try:
            result = bool(entry.check_fn())
        except Exception:
            result = False
        entry._check_result = result
        entry._check_ts = now
        return result

    def invalidate_cache(self) -> None:
        with self._rt_lock:
            for entry in self._tools.values():
                entry._check_result = None
                entry._check_ts = 0


# Singleton
registry = ToolRegistry()


def _is_registry_register_call(node: ast.AST) -> bool:
    if not isinstance(node, ast.Expr) or not isinstance(node.value, ast.Call):
        return False
    func = node.value.func
    return (isinstance(func, ast.Attribute) and func.attr == "register"
            and isinstance(func.value, ast.Name) and func.value.id == "registry")


def _module_registers_tools(module_path: Path) -> bool:
    try:
        source = module_path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(module_path))
    except (OSError, SyntaxError):
        return False
    return any(_is_registry_register_call(stmt) for stmt in tree.body)


def discover_builtin_tools(tools_dir: Optional[Path] = None) -> List[str]:
    """Import built-in self-registering tool modules."""
    tools_path = tools_dir or Path(__file__).resolve().parent
    module_names = [
        f"wolf.tools.{path.stem}"
        for path in sorted(tools_path.glob("*.py"))
        if path.name not in {"__init__.py", "registry.py"}
        and _module_registers_tools(path)
    ]

    imported = []
    for mod_name in module_names:
        try:
            importlib.import_module(mod_name)
            imported.append(mod_name)
        except Exception as e:
            logger.warning(f"Failed to import tool module {mod_name}: {e}")
    return imported
