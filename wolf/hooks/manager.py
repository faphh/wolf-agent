"""Hook Manager — Pre/post lifecycle hooks for tools and conversation."""

import logging
from typing import Any, Callable, Dict, List
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class Hook:
    name: str
    event: str  # "pre_tool", "post_tool", "pre_llm", "post_llm", "on_error"
    handler: Callable
    priority: int = 0
    enabled: bool = True


class HookManager:
    def __init__(self):
        self._hooks: Dict[str, List[Hook]] = {}

    def register(self, name: str, event: str, handler: Callable, priority: int = 0):
        hook = Hook(name=name, event=event, handler=handler, priority=priority)
        self._hooks.setdefault(event, []).append(hook)
        self._hooks[event].sort(key=lambda h: h.priority)

    def unregister(self, name: str):
        for event in self._hooks:
            self._hooks[event] = [h for h in self._hooks[event] if h.name != name]

    def trigger(self, event: str, context: Dict[str, Any]) -> Dict[str, Any]:
        for hook in self._hooks.get(event, []):
            if not hook.enabled:
                continue
            try:
                result = hook.handler(context)
                if isinstance(result, dict):
                    context.update(result)
                if result is False:
                    context["_hook_abort"] = True
                    break
            except Exception as e:
                logger.error(f"Hook {hook.name} failed on {event}: {e}")
        return context

    def list_hooks(self) -> List[Dict[str, Any]]:
        result = []
        for event, hooks in self._hooks.items():
            for h in hooks:
                result.append({"name": h.name, "event": event,
                               "priority": h.priority, "enabled": h.enabled})
        return result


hook_manager = HookManager()
