"""Context Compressor — Keep conversations within token limits.

Three-layer strategy:
1. Snip — truncate large tool outputs (cheap, no LLM needed)
2. Summarize — use LLM to compress old turns (preserves semantics)
3. Drop — remove oldest turns entirely (last resort)

Triggered:
- Pre-flight check before each API call
- On context_overflow error from provider
"""

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ── Token Estimation ──────────────────────────────────────────────

def estimate_tokens(text: str) -> int:
    """Rough token estimate: ~4 chars per token (works for EN/CN/Code)."""
    return (len(text) + 3) // 4


def estimate_message_tokens(msg: Dict[str, Any]) -> int:
    """Estimate tokens for a single message dict."""
    total = 0
    content = msg.get("content", "")
    if isinstance(content, str):
        total += estimate_tokens(content)
    elif isinstance(content, list):
        for part in content:
            if isinstance(part, dict):
                total += estimate_tokens(json.dumps(part, ensure_ascii=False))
            else:
                total += estimate_tokens(str(part))

    # Tool calls
    for tc in msg.get("tool_calls", []):
        total += estimate_tokens(json.dumps(tc, ensure_ascii=False))

    # Role + name overhead
    total += 10
    return total


def estimate_messages_tokens(messages: List[Dict[str, Any]]) -> int:
    """Estimate total tokens for a message list."""
    return sum(estimate_message_tokens(m) for m in messages)


def estimate_request_tokens(messages: List[Dict[str, Any]],
                            system_prompt: str = "",
                            tools: Optional[List[Dict[str, Any]]] = None) -> int:
    """Estimate tokens for a full API request."""
    total = 0
    if system_prompt:
        total += estimate_tokens(system_prompt)
    total += estimate_messages_tokens(messages)
    if tools:
        total += estimate_tokens(json.dumps(tools, ensure_ascii=False))
    return total


# ── Context Window Limits ─────────────────────────────────────────

# Default context windows by provider family
CONTEXT_WINDOWS = {
    "claude-sonnet-4-20250514": 200_000,
    "claude-opus-4-20250514": 200_000,
    "claude-3-5-sonnet": 200_000,
    "mimo-v2.5-pro": 128_000,
    "mimo-v2.5": 128_000,
    "deepseek-chat": 64_000,
    "gpt-4o": 128_000,
    "gpt-4-turbo": 128_000,
}

def get_context_window(model: str) -> int:
    """Get context window size for a model."""
    model_lower = model.lower()
    for key, size in CONTEXT_WINDOWS.items():
        if key in model_lower:
            return size
    # Default: assume 128K
    return 128_000


# ── Compression Config ────────────────────────────────────────────

@dataclass
class CompressionConfig:
    """Configuration for context compression."""
    # Trigger when estimated tokens exceed this fraction of context window
    trigger_ratio: float = 0.75  # 75% of context window
    # Target after compression
    target_ratio: float = 0.50  # compress down to 50%
    # Max tool output length (chars) before snipping
    max_tool_output_chars: int = 8000
    # Number of recent turns to protect from compression
    protect_last_n_turns: int = 4
    # Whether to use LLM for summarization
    use_llm_summary: bool = True
    # Max tokens for summary
    summary_max_tokens: int = 1000


# ── Compressor ────────────────────────────────────────────────────

class ContextCompressor:
    """Compress conversation history to fit within token limits."""

    def __init__(self, config: Optional[CompressionConfig] = None):
        self.config = config or CompressionConfig()
        self._compress_count = 0

    def check_and_compress(self, messages: List[Dict[str, Any]],
                           system_prompt: str = "",
                           tools: Optional[List[Dict[str, Any]]] = None,
                           model: str = "",
                           provider=None) -> Tuple[List[Dict[str, Any]], bool]:
        """Check if compression is needed and apply it.

        Returns (messages, was_compressed).
        """
        context_window = get_context_window(model)
        trigger_threshold = int(context_window * self.config.trigger_ratio)
        target_tokens = int(context_window * self.config.target_ratio)

        estimated = estimate_request_tokens(messages, system_prompt, tools)

        if estimated <= trigger_threshold:
            return messages, False

        logger.info(
            f"Context compression triggered: {estimated} tokens > "
            f"{trigger_threshold} threshold (window: {context_window})"
        )

        # Layer 1: Snip large tool outputs (always, no LLM needed)
        messages = self._snip_tool_outputs(messages)

        # Re-check after snipping
        estimated = estimate_request_tokens(messages, system_prompt, tools)
        if estimated <= target_tokens:
            logger.info(f"After snipping: {estimated} tokens — within target")
            return messages, True

        # Layer 2: Summarize old turns with LLM
        if self.config.use_llm_summary and provider:
            messages = self._summarize_old_turns(messages, provider, model, target_tokens)
            estimated = estimate_request_tokens(messages, system_prompt, tools)
            if estimated <= target_tokens:
                logger.info(f"After summarization: {estimated} tokens — within target")
                return messages, True

        # Layer 3: Drop oldest turns (last resort)
        messages = self._drop_old_turns(messages, target_tokens, system_prompt, tools)
        self._compress_count += 1
        logger.info(f"After dropping: {estimate_request_tokens(messages, system_prompt, tools)} tokens")
        return messages, True

    def _snip_tool_outputs(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Truncate large tool outputs to max_tool_output_chars."""
        max_chars = self.config.max_tool_output_chars
        snipped = 0

        for msg in messages:
            if msg.get("role") != "tool":
                continue
            content = msg.get("content", "")
            if isinstance(content, str) and len(content) > max_chars:
                # Keep first 60% and last 20%
                head = int(max_chars * 0.6)
                tail = int(max_chars * 0.2)
                msg["content"] = (
                    content[:head]
                    + f"\n\n... [snipped: {len(content)} chars → {max_chars}] ...\n\n"
                    + content[-tail:]
                )
                snipped += 1

        if snipped:
            logger.info(f"Snipped {snipped} large tool outputs")
        return messages

    def _summarize_old_turns(self, messages: List[Dict[str, Any]],
                             provider, model: str,
                             target_tokens: int) -> List[Dict[str, Any]]:
        """Use LLM to summarize old conversation turns."""
        protect_n = self.config.protect_last_n_turns

        if len(messages) <= protect_n + 2:
            return messages  # Too few messages to compress

        # Split: old (to summarize) + recent (to keep)
        split_point = len(messages) - protect_n
        old_messages = messages[:split_point]
        recent_messages = messages[split_point:]

        # Build summary prompt
        old_text = self._messages_to_text(old_messages)
        summary_prompt = [
            {"role": "system", "content": (
                "You are a conversation summarizer. Summarize the following "
                "conversation history concisely, preserving:\n"
                "1. Key decisions and conclusions\n"
                "2. Important facts discovered\n"
                "3. Files modified or created\n"
                "4. Current task state and progress\n"
                "5. Any errors encountered and their resolutions\n\n"
                "Keep the summary under 500 words. Output ONLY the summary."
            )},
            {"role": "user", "content": old_text},
        ]

        try:
            from wolf.providers.base import Message
            api_messages = [Message(role=m["role"], content=m["content"]) for m in summary_prompt]
            response = provider.chat(api_messages, model, max_tokens=self.config.summary_max_tokens)

            if response.content and response.finish_reason != "error":
                summary_msg = {
                    "role": "user",
                    "content": (
                        f"[Context Summary — previous {len(old_messages)} messages compressed]\n\n"
                        f"{response.content}\n\n"
                        f"[End of summary. Recent conversation continues below.]"
                    ),
                }
                result = [summary_msg] + recent_messages
                logger.info(
                    f"Summarized {len(old_messages)} messages into summary "
                    f"({estimate_messages_tokens(old_messages)} → "
                    f"{estimate_message_tokens(summary_msg)} tokens)"
                )
                return result
        except Exception as e:
            logger.warning(f"LLM summarization failed: {e}, falling back to drop")

        return messages

    def _drop_old_turns(self, messages: List[Dict[str, Any]],
                        target_tokens: int,
                        system_prompt: str,
                        tools: Optional[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
        """Drop oldest turns to reach target. Last resort."""
        protect_n = self.config.protect_last_n_turns

        if len(messages) <= protect_n:
            return messages

        # Keep a boundary marker
        marker = {
            "role": "user",
            "content": "[Earlier conversation context was compressed to fit within token limits.]",
        }

        # Progressively drop from the front
        result = list(messages)
        while len(result) > protect_n + 1:
            estimated = estimate_request_tokens([marker] + result, system_prompt, tools)
            if estimated <= target_tokens:
                break
            # Drop the oldest non-marker message
            result.pop(0)

        return [marker] + result

    def _messages_to_text(self, messages: List[Dict[str, Any]]) -> str:
        """Convert messages to readable text for summarization."""
        parts = []
        for msg in messages:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            if isinstance(content, list):
                content = json.dumps(content, ensure_ascii=False, indent=2)

            if role == "tool":
                # Truncate tool outputs for summary input
                if len(content) > 2000:
                    content = content[:1500] + "\n... [truncated] ..."
                parts.append(f"[Tool Result]: {content}")
            elif role == "assistant":
                # Include tool calls info
                tool_calls = msg.get("tool_calls", [])
                tc_info = ""
                if tool_calls:
                    tc_names = [tc.get("name", "?") for tc in tool_calls]
                    tc_info = f" (called: {', '.join(tc_names)})"
                parts.append(f"Assistant{tc_info}: {content[:1000]}")
            else:
                parts.append(f"{role.title()}: {content[:1000]}")

        return "\n\n".join(parts)

    @property
    def compression_count(self) -> int:
        return self._compress_count
