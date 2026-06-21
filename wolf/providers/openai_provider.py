"""OpenAI-compatible Provider (works with OpenAI, DeepSeek, MiMo, Ollama, etc.)."""

import json
import logging
from typing import Any, AsyncIterator, Dict, List, Optional

from wolf.providers.base import (
    LLMResponse, Message, Provider, StreamChunk, ToolCall, register_provider,
)

logger = logging.getLogger(__name__)


class OpenAICompatibleProvider(Provider):
    """Provider for any OpenAI-compatible API."""

    def __init__(self, name: str, config: Dict[str, Any]):
        super().__init__(name, config)
        try:
            from openai import OpenAI, AsyncOpenAI
            kwargs = {"api_key": self.api_key}
            if self.base_url:
                kwargs["base_url"] = self.base_url
            self._client = OpenAI(**kwargs)
            self._async_client = AsyncOpenAI(**kwargs)
        except ImportError:
            raise ImportError("openai package required: pip install openai")

    def get_tool_definitions_format(self, tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return tools  # Already in OpenAI format

    def chat(self, messages: List[Message], model: str,
             tools: Optional[List[Dict[str, Any]]] = None,
             stream: bool = False, **kwargs) -> LLMResponse:
        api_messages = self.format_messages(messages)
        params: Dict[str, Any] = {
            "model": model or self.default_model,
            "messages": api_messages,
            "max_tokens": kwargs.get("max_tokens", self.max_tokens),
        }
        if tools:
            params["tools"] = tools

        try:
            response = self._client.chat.completions.create(**params)
        except Exception as e:
            return LLMResponse(content="", finish_reason="error", provider=self.name,
                               usage={"error": str(e)})

        choice = response.choices[0] if response.choices else None
        if not choice:
            return LLMResponse(content="", finish_reason="empty", provider=self.name)

        msg = choice.message
        tool_calls = []
        if msg.tool_calls:
            for tc in msg.tool_calls:
                try:
                    args = json.loads(tc.function.arguments)
                except json.JSONDecodeError:
                    args = {"raw": tc.function.arguments}
                tool_calls.append(ToolCall(
                    id=tc.id, name=tc.function.name, arguments=args,
                ))

        usage = {}
        if response.usage:
            usage = {
                "input_tokens": response.usage.prompt_tokens,
                "output_tokens": response.usage.completion_tokens,
            }

        return LLMResponse(
            content=msg.content or "",
            tool_calls=tool_calls,
            finish_reason=choice.finish_reason or "",
            usage=usage,
            model=response.model,
            provider=self.name,
            raw=response,
        )

    async def chat_stream(self, messages: List[Message], model: str,
                          tools: Optional[List[Dict[str, Any]]] = None,
                          **kwargs) -> AsyncIterator[StreamChunk]:
        api_messages = self.format_messages(messages)
        params: Dict[str, Any] = {
            "model": model or self.default_model,
            "messages": api_messages,
            "max_tokens": kwargs.get("max_tokens", self.max_tokens),
            "stream": True,
        }
        if tools:
            params["tools"] = tools

        try:
            stream = await self._async_client.chat.completions.create(**params)
            current_tool_id = ""
            async for chunk in stream:
                delta = chunk.choices[0].delta if chunk.choices else None
                if not delta:
                    continue
                if delta.content:
                    yield StreamChunk(type="text", content=delta.content)
                if delta.tool_calls:
                    for tc_delta in delta.tool_calls:
                        if tc_delta.id:
                            current_tool_id = tc_delta.id
                            yield StreamChunk(
                                type="tool_use_start",
                                tool_call_id=tc_delta.id,
                                tool_name=tc_delta.function.name if tc_delta.function else "",
                            )
                        if tc_delta.function and tc_delta.function.arguments:
                            yield StreamChunk(
                                type="tool_use_delta",
                                tool_call_id=current_tool_id,
                                tool_input_delta=tc_delta.function.arguments,
                            )
            yield StreamChunk(type="done")
        except Exception as e:
            yield StreamChunk(type="error", error=str(e))


register_provider("openai", OpenAICompatibleProvider)
register_provider("xiaomi", OpenAICompatibleProvider)
register_provider("deepseek", OpenAICompatibleProvider)
register_provider("ollama", OpenAICompatibleProvider)
