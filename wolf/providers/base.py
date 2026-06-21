"""Provider base class and factory."""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class Message:
    """Standardized message format."""
    role: str  # "system" | "user" | "assistant" | "tool"
    content: str = ""
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)
    tool_call_id: str = ""
    name: str = ""
    thinking: str = ""  # Extended thinking content


@dataclass
class ToolCall:
    """Standardized tool call."""
    id: str
    name: str
    arguments: Dict[str, Any]


@dataclass
class LLMResponse:
    """Standardized LLM response."""
    content: str = ""
    tool_calls: List[ToolCall] = field(default_factory=list)
    thinking: str = ""
    finish_reason: str = ""
    usage: Dict[str, Any] = field(default_factory=dict)
    model: str = ""
    provider: str = ""
    raw: Any = None


@dataclass
class StreamChunk:
    """A chunk from streaming response."""
    type: str  # "text" | "tool_use_start" | "tool_use_delta" | "thinking" | "done" | "error"
    content: str = ""
    tool_call_id: str = ""
    tool_name: str = ""
    tool_input_delta: str = ""
    error: str = ""


class Provider(ABC):
    """Abstract base class for LLM providers."""

    def __init__(self, name: str, config: Dict[str, Any]):
        self.name = name
        self.config = config
        self.api_key = config.get("api_key", "")
        self.base_url = config.get("base_url", "")
        self.default_model = config.get("default_model", "")
        self.max_tokens = config.get("max_tokens", 8192)

    @abstractmethod
    def chat(self, messages: List[Message], model: str,
             tools: Optional[List[Dict[str, Any]]] = None,
             stream: bool = False, **kwargs) -> LLMResponse:
        """Send a chat completion request."""
        ...

    @abstractmethod
    def chat_stream(self, messages: List[Message], model: str,
                    tools: Optional[List[Dict[str, Any]]] = None,
                    **kwargs) -> AsyncIterator[StreamChunk]:
        """Stream a chat completion response."""
        ...

    @abstractmethod
    def get_tool_definitions_format(self, tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Convert tool definitions to provider-specific format."""
        ...

    def format_messages(self, messages: List[Message],
                        tools: Optional[List[Dict[str, Any]]] = None) -> List[Dict[str, Any]]:
        """Format messages for the provider API. Override for provider-specific formatting."""
        result = []
        for msg in messages:
            if msg.role == "system":
                result.append({"role": "system", "content": msg.content})
            elif msg.role == "user":
                result.append({"role": "user", "content": msg.content})
            elif msg.role == "assistant":
                m: Dict[str, Any] = {"role": "assistant", "content": msg.content}
                if msg.tool_calls:
                    m["tool_calls"] = [
                        {"id": tc["id"], "type": "function",
                         "function": {"name": tc["name"], "arguments": tc.get("arguments", "{}")}}
                        for tc in msg.tool_calls
                    ]
                result.append(m)
            elif msg.role == "tool":
                result.append({
                    "role": "tool", "content": msg.content,
                    "tool_call_id": msg.tool_call_id,
                })
        return result


# Provider registry
_provider_classes: Dict[str, type] = {}


def register_provider(name: str, cls: type):
    _provider_classes[name] = cls


def create_provider(name: str, config: Dict[str, Any]) -> Provider:
    cls = _provider_classes.get(name)
    if cls is None:
        raise ValueError(f"Unknown provider: {name}. Available: {list(_provider_classes.keys())}")
    return cls(name=name, config=config)
