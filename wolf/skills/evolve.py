"""Self-Evolution Engine — Auto-extract skills from successful patterns.

After completing complex tasks, Wolf analyzes the conversation and
extracts reusable patterns as new skills.
"""

import os
import re
import yaml
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

SKILLS_DIR = Path.home() / ".wolf" / "skills"


def analyze_and_evolve(messages: List[Dict[str, Any]], response: str) -> Optional[str]:
    """Analyze a conversation turn and extract a skill if pattern is reusable.

    Returns the skill name if created, None otherwise.
    """
    # Only extract skills from successful complex tasks (5+ tool calls)
    tool_calls = [m for m in messages if m.get("role") == "tool"]
    if len(tool_calls) < 5:
        return None

    # Check for error patterns — don't extract failed approaches
    has_errors = any("error" in str(m.get("content", "")) for m in tool_calls[-3:])
    if has_errors:
        return None

    # Look for patterns that suggest a reusable workflow
    tool_sequence = [m.get("name", "") for m in tool_calls if m.get("name")]
    if _is_meaningful_sequence(tool_sequence):
        skill_name = _suggest_skill_name(tool_sequence, response)
        if skill_name:
            _create_skill(skill_name, tool_sequence, messages)
            return skill_name

    return None


def _is_meaningful_sequence(tools: List[str]) -> bool:
    """Check if tool usage pattern is worth extracting."""
    # Multi-tool workflows are interesting
    unique_tools = set(tools)
    if len(unique_tools) >= 3:
        return True
    # Repeated patterns are interesting
    if len(tools) >= 8:
        return True
    return False


def _suggest_skill_name(tools: List[str], response: str) -> Optional[str]:
    """Suggest a skill name from the tool sequence."""
    # Extract key verbs/nouns from response
    words = re.findall(r"\b[a-z]{4,}\b", response[:200].lower())
    if not words:
        return None
    # Use first meaningful word + tool context
    key_words = [w for w in words if w not in {"this", "that", "with", "from", "have", "been", "will"}]
    if key_words:
        return "-".join(key_words[:3])
    return None


def _create_skill(name: str, tools: List[str], messages: List[Dict[str, Any]]):
    """Create a new skill from conversation pattern."""
    SKILLS_DIR.mkdir(parents=True, exist_ok=True)
    skill_dir = SKILLS_DIR / name
    skill_dir.mkdir(exist_ok=True)

    # Build skill content
    unique_tools = list(dict.fromkeys(tools))
    content = f"""---
name: {name}
description: "Auto-extracted skill from successful workflow"
tags: [auto-extracted]
tools_used: {unique_tools}
---

# {name}

Auto-extracted from a successful workflow using: {", ".join(unique_tools)}

## Steps
1. Review the task requirements
2. Use the tools in the pattern: {" → ".join(unique_tools[:5])}

## Notes
This skill was auto-generated. Review and refine it manually.
"""
    (skill_dir / "SKILL.md").write_text(content, encoding="utf-8")
    logger.info(f"Auto-extracted skill: {name}")
