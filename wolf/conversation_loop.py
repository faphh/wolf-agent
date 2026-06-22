"""Wolf Conversation Loop — The heart of the agent.

Fusion of Hermes robust retry/fallback + Claude Code streaming tool execution.
"""

import json
import logging
import time
import uuid
from typing import Any, Dict, List, Optional

from wolf.providers.base import LLMResponse, Message, Provider, StreamChunk, ToolCall
from wolf.tools.registry import registry
from wolf.context.compressor import ContextCompressor, CompressionConfig

logger = logging.getLogger(__name__)


class ConversationLoop:
    """Core conversation loop that drives the Wolf agent."""

    def __init__(self, provider: Provider, model: str, config: Dict[str, Any],
                 toolsets: Optional[List[str]] = None,
                 fallback_providers: Optional[List[tuple]] = None):
        self.provider = provider
        self.model = model
        self.config = config
        self.toolsets = toolsets
        self.fallback_providers = fallback_providers or []
        self.max_iterations = config.get("max_iterations", 50)
        self.max_retries = config.get("max_retries", 3)
        self.timeout = config.get("timeout", 300)
        self.stream = config.get("stream", True)
        self.messages: List[Message] = []
        self.total_usage: Dict[str, int] = {"input_tokens": 0, "output_tokens": 0}
        self.total_cost: float = 0
        self._interrupted = False
        self.compressor = ContextCompressor(CompressionConfig(
            trigger_ratio=0.75,
            target_ratio=0.50,
            max_tool_output_chars=8000,
            protect_last_n_turns=4,
        ))

    def interrupt(self):
        self._interrupted = True

    def reset(self):
        self._interrupted = False

    def run(self, user_message: str, system_prompt: str = "",
            callback=None) -> str:
        """Run one conversation turn.

        Args:
            user_message: The user's input
            system_prompt: System prompt (memory + skills + context)
            callback: Optional callback for streaming output: callback(chunk: StreamChunk)

        Returns:
            The final assistant response text
        """
        self._interrupted = False

        # Store system_prompt for compression callbacks
        self._current_system_prompt = system_prompt

        # Add user message
        self.messages.append(Message(role="user", content=user_message))

        # Get tool definitions
        tools = self._get_tool_definitions()

        iteration = 0
        while iteration < self.max_iterations:
            if self._interrupted:
                break
            iteration += 1

            # Build API messages with system prompt
            api_messages = self._build_api_messages(system_prompt)

            # Call LLM
            response = self._call_llm(api_messages, tools, callback)

            if response is None:
                return "(Wolf: No response from model)"

            # Track usage
            self._track_usage(response)

            # Handle response
            if response.finish_reason == "error":
                error_msg = response.usage.get("error", "Unknown error")
                logger.error(f"LLM error: {error_msg}")
                return f"(Wolf error: {error_msg})"

            # Add assistant message to history
            self.messages.append(Message(
                role="assistant",
                content=response.content,
                tool_calls=[{"id": tc.id, "name": tc.name,
                             "arguments": json.dumps(tc.arguments) if isinstance(tc.arguments, dict) else tc.arguments}
                            for tc in response.tool_calls],
                thinking=response.thinking,
            ))

            # If no tool calls, we're done
            if not response.tool_calls:
                return response.content

            # Execute tool calls
            tool_results = self._execute_tools(response.tool_calls, callback)

            # Add tool results to messages
            for result in tool_results:
                self.messages.append(Message(
                    role="tool",
                    content=json.dumps(result["result"], ensure_ascii=False) if not isinstance(result["result"], str) else result["result"],
                    tool_call_id=result["tool_call_id"],
                    name=result["tool_name"],
                ))

        if iteration >= self.max_iterations:
            return "(Wolf: Max iterations reached)"

        return "(Wolf: Conversation interrupted)"

    def _get_tool_definitions(self) -> List[Dict[str, Any]]:
        """Get tool definitions in the provider's format."""
        raw = registry.get_tool_definitions(self.toolsets)
        return self.provider.get_tool_definitions_format(raw)

    def _build_api_messages(self, system_prompt: str) -> List[Message]:
        """Build messages list with system prompt prepended and compression applied."""
        # Convert to dict format for compressor
        msg_dicts = []
        for m in self.messages:
            d = {"role": m.role, "content": m.content}
            if m.tool_calls:
                d["tool_calls"] = m.tool_calls
            if m.tool_call_id:
                d["tool_call_id"] = m.tool_call_id
            if m.name:
                d["name"] = m.name
            msg_dicts.append(d)

        # Get tool definitions for accurate estimation
        tools = self._get_tool_definitions()

        # Apply compression if needed
        compressed_dicts, was_compressed = self.compressor.check_and_compress(
            msg_dicts, system_prompt=system_prompt, tools=tools,
            model=self.model, provider=self.provider,
        )

        if was_compressed:
            # Rebuild Message objects from compressed dicts
            self.messages = [
                Message(role=d["role"], content=d.get("content", ""),
                        tool_calls=d.get("tool_calls", []),
                        tool_call_id=d.get("tool_call_id", ""),
                        name=d.get("name", ""))
                for d in compressed_dicts
            ]

        # Build final messages with system prompt
        messages = []
        if system_prompt:
            messages.append(Message(role="system", content=system_prompt))
        messages.extend(self.messages)
        return messages

    def _call_llm(self, messages: List[Message], tools: List[Dict[str, Any]],
                  callback=None) -> Optional[LLMResponse]:
        """Call LLM with retry and fallback."""
        providers = [(self.provider, self.model)] + self.fallback_providers

        for provider, model in providers:
            for retry in range(self.max_retries):
                if self._interrupted:
                    return None

                try:
                    if self.stream and callback:
                        return self._call_llm_streaming(messages, tools, provider, model, callback)
                    else:
                        response = provider.chat(messages, model, tools=tools)
                        if response.finish_reason != "error":
                            return response
                        # Check for context overflow — trigger emergency compression
                        error_msg = response.usage.get("error", "")
                        if self._is_context_overflow(error_msg):
                            logger.warning("Context overflow detected, triggering emergency compression")
                            self._emergency_compress()
                            # Rebuild messages and retry once
                            messages = self._build_api_messages(self._current_system_prompt)
                            response = provider.chat(messages, model, tools=tools)
                            if response.finish_reason != "error":
                                return response
                        # Retry on error
                        if retry < self.max_retries - 1:
                            time.sleep(2 ** retry)
                            continue
                except Exception as e:
                    logger.error(f"LLM call failed (provider={provider.name}, retry={retry}): {e}")
                    if retry < self.max_retries - 1:
                        time.sleep(2 ** retry)
                    continue

            # Try next fallback provider
            logger.warning(f"Provider {provider.name} exhausted retries, trying fallback...")

        return None

    def _call_llm_streaming(self, messages: List[Message], tools: List[Dict[str, Any]],
                            provider: Provider, model: str, callback) -> LLMResponse:
        """Call LLM with streaming."""
        import asyncio

        async def _stream():
            content_parts = []
            tool_calls_data: Dict[str, Dict] = {}
            thinking_parts = []

            async for chunk in provider.chat_stream(messages, model, tools=tools):
                if self._interrupted:
                    break
                callback(chunk)

                if chunk.type == "text":
                    content_parts.append(chunk.content)
                elif chunk.type == "thinking":
                    thinking_parts.append(chunk.content)
                elif chunk.type == "tool_use_start":
                    tool_calls_data[chunk.tool_call_id] = {
                        "id": chunk.tool_call_id,
                        "name": chunk.tool_name,
                        "arguments": "",
                    }
                elif chunk.type == "tool_use_delta":
                    if chunk.tool_call_id in tool_calls_data:
                        tool_calls_data[chunk.tool_call_id]["arguments"] += chunk.tool_input_delta

            tool_calls = []
            for tc_data in tool_calls_data.values():
                try:
                    args = json.loads(tc_data["arguments"]) if tc_data["arguments"] else {}
                except json.JSONDecodeError:
                    args = {"raw": tc_data["arguments"]}
                tool_calls.append(ToolCall(
                    id=tc_data["id"], name=tc_data["name"], arguments=args,
                ))

            return LLMResponse(
                content="".join(content_parts),
                tool_calls=tool_calls,
                thinking="".join(thinking_parts),
                finish_reason="tool_use" if tool_calls else "end_turn",
                provider=provider.name,
                model=model,
            )

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    future = pool.submit(asyncio.run, _stream())
                    return future.result(timeout=self.timeout)
            else:
                return asyncio.run(_stream())
        except Exception as e:
            logger.error(f"Streaming failed: {e}")
            # Fallback to non-streaming
            return provider.chat(messages, model, tools=tools)

    def _execute_tools(self, tool_calls: List[ToolCall],
                       callback=None) -> List[Dict[str, Any]]:
        """Execute tool calls with permission check and hook support."""
        from wolf.hooks.manager import hook_manager
        from wolf.permissions import permission_manager
        results = []
        for tc in tool_calls:
            if self._interrupted:
                break

            # Permission check
            perm = permission_manager.check_permission(tc.name, tc.arguments)
            if not perm.allowed:
                if perm.needs_user_input:
                    # Auto-approve for now (interactive handled by CLI)
                    permission_manager.approve(tc.name)
                else:
                    results.append({"tool_call_id": tc.id, "tool_name": tc.name,
                                    "result": {"error": f"Permission denied: {perm.reason}"}})
                    continue

            # Pre-tool hook
            ctx = hook_manager.trigger("pre_tool", {
                "tool_name": tc.name, "arguments": tc.arguments,
            })
            if ctx.get("_hook_abort"):
                results.append({"tool_call_id": tc.id, "tool_name": tc.name,
                                "result": {"error": "Aborted by pre-tool hook"}})
                continue

            start_time = time.time()
            result = registry.dispatch(tc.name, tc.arguments)
            elapsed = time.time() - start_time

            # Post-tool hook
            hook_manager.trigger("post_tool", {
                "tool_name": tc.name, "result": result, "elapsed": elapsed,
            })

            if callback:
                callback(StreamChunk(
                    type="tool_result",
                    content=f"[{tc.name}] {'✓' if 'error' not in result else '✗'} ({elapsed:.1f}s)",
                    tool_call_id=tc.id, tool_name=tc.name,
                ))

            results.append({
                "tool_call_id": tc.id, "tool_name": tc.name, "result": result,
            })

        return results

    def _track_usage(self, response: LLMResponse):
        """Track token usage."""
        if response.usage:
            self.total_usage["input_tokens"] += response.usage.get("input_tokens", 0)
            self.total_usage["output_tokens"] += response.usage.get("output_tokens", 0)

    def _is_context_overflow(self, error_msg: str) -> bool:
        """Check if error indicates context overflow."""
        overflow_signals = [
            "context_length_exceeded", "context window", "too long",
            "too many tokens", "maximum context", "context_length",
            "prompt is too long", "max_tokens", "context limit",
        ]
        error_lower = error_msg.lower()
        return any(s in error_lower for s in overflow_signals)

    def _emergency_compress(self, system_prompt: str = ""):
        """Emergency compression when context_overflow is detected."""
        from wolf.context.compressor import estimate_request_tokens, get_context_window
        # Force aggressive compression
        self.compressor.config.trigger_ratio = 0.5
        self.compressor.config.target_ratio = 0.35
        self.compressor.config.max_tool_output_chars = 4000
        logger.info("Emergency compression mode activated")

    def get_usage_summary(self) -> str:
        comp = self.compressor.compression_count
        comp_info = f", {comp} compressions" if comp > 0 else ""
        return (f"Tokens: {self.total_usage['input_tokens']} in / "
                f"{self.total_usage['output_tokens']} out{comp_info}")
