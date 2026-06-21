"""Anthropic Claude Provider."""

import json
import logging
from typing import Any, AsyncIterator, Dict, List, Optional

from wolf.providers.base import (
    LLMResponse, Message, Provider, StreamChunk, ToolCall, register_provider,
)

logger = logging.getLogger(__name__)


class AnthropicProvider(Provider):
    """Anthropic Claude API provider."""

    def __init__(self, name: str, config: Dict[str, Any]):
        super().__init__(name, config)
        try:
            import anthropic
            self._client = anthropic.Anthropic(api_key=self.api_key)
        except ImportError:
            raise ImportError("anthropic package required: pip install anthropic")

    def _format_messages(self, messages: List[Message]) -> tuple:
        """Split system prompt from messages for Anthropic API."""
        system_parts = []
        api_messages = []
        for msg in messages:
            if msg.role == "system":
                system_parts.append(msg.content)
            elif msg.role == "user":
                api_messages.append({"role": "user", "content": msg.content})
            elif msg.role == "assistant":
                content_blocks = []
                if msg.thinking:
                    content_blocks.append({"type": "thinking", "thinking": msg.thinking})
                if msg.content:
                    content_blocks.append({"type": "text", "text": msg.content})
                for tc in msg.tool_calls:
                    content_blocks.append({
                        "type": "tool_use",
                        "id": tc["id"],
                        "name": tc["name"],
                        "input": json.loads(tc["arguments"]) if isinstance(tc["arguments"], str) else tc["arguments"],
                    })
                if content_blocks:
                    api_messages.append({"role": "assistant", "content": content_blocks})
            elif msg.role == "tool":
                api_messages.append({
                    "role": "user",
                    "content": [{
                        "type": "tool_result",
                        "tool_use_id": msg.tool_call_id,
                        "content": msg.content,
                    }],
                })
        return "\n\n".join(system_parts), api_messages

    def _format_tools(self, tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Convert to Anthropic tool format."""
        result = []
        for t in tools:
            if "function" in t:
                fn = t["function"]
                result.append({
                    "name": fn["name"],
                    "description": fn.get("description", ""),
                    "input_schema": fn.get("parameters", {"type": "object", "properties": {}}),
                })
            else:
                result.append(t)
        return result

    def get_tool_definitions_format(self, tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return self._format_tools(tools)

    def chat(self, messages: List[Message], model: str,
             tools: Optional[List[Dict[str, Any]]] = None,
             stream: bool = False, **kwargs) -> LLMResponse:
        system, api_messages = self._format_messages(messages)
        params: Dict[str, Any] = {
            "model": model or self.default_model,
            "max_tokens": kwargs.get("max_tokens", self.max_tokens),
            "messages": api_messages,
        }
        if system:
            params["system"] = system
        if tools:
            params["tools"] = self._format_tools(tools)

        try:
            response = self._client.messages.create(**params)
        except Exception as e:
            return LLMResponse(content="", finish_reason="error", provider=self.name,
                               usage={"error": str(e)})

        # Parse response
        content_parts = []
        tool_calls = []
        thinking = ""
        for block in response.content:
            if block.type == "text":
                content_parts.append(block.text)
            elif block.type == "tool_use":
                tool_calls.append(ToolCall(
                    id=block.id, name=block.name,
                    arguments=block.input if isinstance(block.input, dict)
                    else json.loads(block.input),
                ))
            elif block.type == "thinking":
                thinking = block.thinking

        usage = {}
        if response.usage:
            usage = {
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens,
            }

        return LLMResponse(
            content="\n".join(content_parts),
            tool_calls=tool_calls,
            thinking=thinking,
            finish_reason=response.stop_reason or "",
            usage=usage,
            model=response.model,
            provider=self.name,
            raw=response,
        )

    async def chat_stream(self, messages: List[Message], model: str,
                          tools: Optional[List[Dict[str, Any]]] = None,
                          **kwargs) -> AsyncIterator[StreamChunk]:
        system, api_messages = self._format_messages(messages)
        params: Dict[str, Any] = {
            "model": model or self.default_model,
            "max_tokens": kwargs.get("max_tokens", self.max_tokens),
            "messages": api_messages,
        }
        if system:
            params["system"] = system
        if tools:
            params["tools"] = self._format_tools(tools)

        current_tool_id = ""
        current_tool_name = ""
        try:
            with self._client.messages.stream(**params) as stream:
                for event in stream:
                    if event.type == "content_block_start":
                        block = event.content_block
                        if hasattr(block, "type"):
                            if block.type == "tool_use":
                                current_tool_id = block.id
                                current_tool_name = block.name
                                yield StreamChunk(
                                    type="tool_use_start",
                                    tool_call_id=block.id,
                                    tool_name=block.name,
                                )
                            elif block.type == "thinking":
                                pass  # thinking block started
                    elif event.type == "content_block_delta":
                        delta = event.delta
                        if hasattr(delta, "type"):
                            if delta.type == "text_delta":
                                yield StreamChunk(type="text", content=delta.text)
                            elif delta.type == "input_json_delta":
                                yield StreamChunk(
                                    type="tool_use_delta",
                                    tool_call_id=current_tool_id,
                                    tool_input_delta=delta.partial_json,
                                )
                            elif delta.type == "thinking_delta":
                                yield StreamChunk(type="thinking", content=delta.thinking)
                    elif event.type == "content_block_stop":
                        if current_tool_id:
                            yield StreamChunk(
                                type="tool_use_end",
                                tool_call_id=current_tool_id,
                                tool_name=current_tool_name,
                            )
                            current_tool_id = ""
                            current_tool_name = ""
                    elif event.type == "message_stop":
                        yield StreamChunk(type="done",
                                          content=event.message.stop_reason if hasattr(event, "message") else "")
        except Exception as e:
            yield StreamChunk(type="error", error=str(e))


register_provider("anthropic", AnthropicProvider)
